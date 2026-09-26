import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from roundtable.knowledge import KnowledgeStore
from roundtable.knowledge_api import create_knowledge_router


def make_zip(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return stream.getvalue()


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "my-addon"
        self.source.mkdir()
        self.store = KnowledgeStore(self.root / "knowledge")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def write(self, path, text):
        destination = self.source / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        return destination

    def test_chinese_and_api_identifiers_retrieve_cited_lines(self):
        self.write("scripts/server.py", "# 玩家背包中添加奖励物品\ndef AddItemToPlayer(playerId):\n    return playerId\n")
        self.write("README.md", "这是中国版模组开发示例。\n")
        repository = self.store.import_path(self.source)
        self.assertEqual(repository["revision"], 1)
        self.assertEqual(repository["file_count"], 2)
        for query in ("玩家背包 奖励物品", "AddItemToPlayer"):
            results = self.store.search(repository["id"], query)
            self.assertTrue(results)
            self.assertEqual(results[0]["path"], "scripts/server.py")
            self.assertEqual(results[0]["start_line"], 1)
            self.assertEqual(results[0]["end_line"], 3)
            self.assertEqual(results[0]["revision"], 1)
        self.assertTrue((self.store.project_root(repository["id"]) / "scripts/server.py").is_file())

    def test_reindex_deduplicates_and_removes_deleted_code(self):
        self.write("old.py", "old_unique_function = 1\n")
        self.write("kept.py", "kept_function = 1\n")
        repository = self.store.import_path(self.source)
        repeated = self.store.import_path(self.source)
        self.assertEqual(repeated["id"], repository["id"])
        self.assertEqual(repeated["revision"], 1)
        self.assertEqual(repeated["stats"]["unchanged"], 2)
        (self.source / "old.py").unlink()
        self.write("kept.py", "replacement_function = 2\n")
        updated = self.store.reindex(repository["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["stats"]["deleted"], 1)
        self.assertEqual(updated["stats"]["changed"], 1)
        self.assertEqual(self.store.search(repository["id"], "old_unique"), [])
        self.assertFalse((self.store.project_root(repository["id"]) / "old.py").exists())
        (self.source / "kept.py").unlink()
        empty = self.store.reindex(repository["id"])
        self.assertEqual(empty["revision"], 3)
        self.assertEqual(empty["file_count"], 0)
        self.assertEqual(empty["chunk_count"], 0)
        self.assertEqual(self.store.search(repository["id"], "replacement"), [])

    def test_excludes_secrets_links_build_and_binary_files(self):
        self.write("safe.py", "ordinary_code = 1\n")
        for path in (".env", ".env.local", "credentials.json", "secret-config.json", ".ssh/id_rsa", "node_modules/code.py", ".git/config.py"):
            self.write(path, "sensitive_value = 'should never be read'\n")
        self.write("config.py", 'API_KEY = "sk-' + 'a' * 40 + '"\n')
        self.write("hidden-key.txt", "-----BEGIN " + "PRIVATE KEY-----\nTOPSECRET\n")
        (self.source / "image.txt").write_bytes(b"\x00binary")
        outside = self.root / "outside.py"
        outside.write_text("outside_secret = 1", encoding="utf-8")
        (self.source / "escape.py").symlink_to(outside)
        (self.source / "escape-dir").symlink_to(self.root, target_is_directory=True)
        os.link(outside, self.source / "hardlink.py")
        item = self.store.import_path(self.source)
        self.assertEqual(item["file_count"], 1)
        self.assertEqual([path.name for path in self.store.project_root(item["id"]).iterdir()], ["safe.py"])
        self.assertEqual(self.store.search(item["id"], "sensitive outside_secret TOPSECRET"), [])

    def test_refuses_broad_relative_and_sensitive_directory_import(self):
        for path in (".", "/", str(Path.home()), "/etc", str(self.store.root)):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.store.import_path(path)

    def test_zip_rejects_traversal_duplicates_symlinks_and_encrypted_paths(self):
        for name in ("../escape.py", "/absolute.py", "a/../../escape.py", "a\\escape.py", "C:/escape.py"):
            with self.subTest(path=name), self.assertRaises(ValueError):
                self.store.import_zip(make_zip({name: "pass"}))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            symlink = zipfile.ZipInfo("evil.py")
            symlink.create_system = 3
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(symlink, "../../outside.py")
        with self.assertRaises(ValueError):
            self.store.import_zip(stream.getvalue())
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("a.py", "safe")
            with self.assertWarns(UserWarning):
                archive.writestr("a.py", "different")
        with self.assertRaises(ValueError):
            self.store.import_zip(stream.getvalue())
        self.assertEqual(self.store.list(), [])

    def test_zip_snapshot_strip_wrapper_no_execution_and_reindex(self):
        marker = self.root / "should-not-exist"
        payload = make_zip({"project/scripts/init.py": f"open({str(marker)!r}, 'w').write('executed')\n",
                            "project/.env": "TOKEN=hidden", "project/README.md": "玩家背包奖励\n"})
        item = self.store.import_zip(payload, "Uploaded mod")
        self.assertFalse(marker.exists())
        self.assertEqual(item["source_type"], "zip")
        self.assertIsNone(item["source_path"])
        self.assertEqual(item["file_count"], 2)
        self.assertTrue((self.store.project_root(item["id"]) / "scripts/init.py").exists())
        self.assertEqual(self.store.reindex(item["id"])["revision"], 1)

    def test_file_count_and_zip_decompression_limits_are_atomic(self):
        payload = make_zip({"file.py": "a" * 100})
        with patch("roundtable.knowledge.MAX_TOTAL_BYTES", 50):
            with self.assertRaises(ValueError):
                self.store.import_zip(payload)
        self.write("one.py", "one = 1\n")
        self.write("two.py", "two = 2\n")
        with patch("roundtable.knowledge.MAX_FILES", 1):
            with self.assertRaises(ValueError):
                self.store.import_path(self.source)
        self.assertEqual(self.store.list(), [])

    def test_accepted_experience_requires_evidence_and_retains_revision(self):
        self.write("main.py", "print('hello')\n")
        item = self.store.import_path(self.source)
        candidate = self.store.add_feedback(item["id"], "背包容量", "先检查背包剩余容量", False)
        self.assertFalse(candidate["accepted"])
        self.assertEqual(self.store.search(item["id"], "背包容量"), [])
        with self.assertRaises(ValueError):
            self.store.add_feedback(item["id"], "背包容量", "先检查容量", True)
        accepted = self.store.add_feedback(item["id"], "背包容量", "先检查背包剩余容量", True,
                                           {"path": "main.py", "validation": "人工检查通过"})
        self.write("main.py", "print('next')\n")
        self.store.reindex(item["id"])
        results = self.store.search(item["id"], "背包容量")
        self.assertEqual(results[0]["source"], "feedback")
        self.assertEqual(results[0]["revision"], 1)
        self.assertEqual(results[0]["evidence"], accepted["evidence"])
        self.assertEqual(len(self.store.feedback(item["id"])), 2)

    def test_review_and_revoke_existing_candidate_preserve_original_revision(self):
        self.write("main.py", "initial = 1\n")
        item = self.store.import_path(self.source)
        candidate = self.store.add_feedback(item["id"], "背包检查", "发奖励前检查背包容量")
        self.write("main.py", "next_revision = 2\n")
        self.store.reindex(item["id"])
        with self.assertRaises(ValueError):
            self.store.review_feedback(item["id"], candidate["id"], True)
        reviewed = self.store.review_feedback(item["id"], candidate["id"], True, "main.py:1 人工检查")
        self.assertEqual(reviewed["revision"], 1)
        self.assertIn("reviewed_at", reviewed)
        self.assertEqual(self.store.search(item["id"], "背包")[0]["source"], "feedback")
        self.store.review_feedback(item["id"], candidate["id"], False)
        self.assertEqual(self.store.search(item["id"], "背包"), [])
        with self.assertRaises(KeyError):
            self.store.review_feedback(item["id"], "missing", False)

    def test_context_freezes_revision_and_old_snapshot_survives_reindex(self):
        self.write("main.py", "first_revision = 1\n")
        item = self.store.import_path(self.source)
        context = self.store.context(item["id"], "first_revision")
        self.write("main.py", "second_revision = 2\n")
        updated = self.store.reindex(item["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(context["repository"]["revision"], 1)
        self.assertEqual(context["hits"][0]["revision"], 1)
        self.assertEqual((context["root"] / "main.py").read_text(), "first_revision = 1\n")

    def test_persistence_and_search_with_fts_fallback(self):
        self.write("main.py", "# 玩家背包奖励\ndef GiveReward(): pass\n")
        item = self.store.import_path(self.source)
        self.store.close()
        self.store = KnowledgeStore(self.root / "knowledge")
        self.assertEqual(self.store.get(item["id"])["file_count"], 1)
        self.store._fts = False
        self.assertEqual(self.store.search(item["id"], "背包奖励")[0]["path"], "main.py")


class KnowledgeAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = KnowledgeStore(Path(self.tmp.name) / "knowledge")
        app = FastAPI()
        app.state.knowledge = self.store
        app.include_router(create_knowledge_router())
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.store.close()
        self.tmp.cleanup()

    def test_upload_retrieve_feedback_reindex_and_validation(self):
        response = self.client.post("/api/repositories/upload?name=Sample", content=make_zip({"main.py": "# 背包奖励\n"}),
                                    headers={"content-type": "application/zip"})
        self.assertEqual(response.status_code, 201, response.text)
        item = response.json()
        endpoint = "/api/repositories/" + item["id"]
        self.assertEqual(len(self.client.get("/api/repositories").json()), 1)
        self.assertEqual(self.client.get(endpoint).json()["name"], "Sample")
        self.assertTrue(self.client.get(endpoint + "/search", params={"q": "背包"}).json())
        self.assertEqual(self.client.post(endpoint + "/reindex").status_code, 200)
        feedback = self.client.post(endpoint + "/feedback", json={"title": "经验", "content": "先检查物品 ID", "accepted": True,
                                                                 "evidence": "main.py:1 人工核对"})
        self.assertEqual(feedback.status_code, 201, feedback.text)
        self.assertEqual(len(self.client.get(endpoint + "/feedback").json()), 1)
        review_endpoint = endpoint + "/feedback/" + feedback.json()["id"]
        revoked = self.client.patch(review_endpoint, json={"accepted": False})
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(revoked.json()["accepted"])
        self.assertEqual(self.client.patch(review_endpoint, json={"accepted": "yes"}).status_code, 422)
        self.assertEqual(self.client.post(endpoint + "/feedback", json={"title": "经验", "content": "正文", "accepted": "false"}).status_code, 422)
        self.assertEqual(self.client.get("/api/repositories/missing").status_code, 404)
        self.assertEqual(self.client.post("/api/repositories/missing/reindex").status_code, 404)
        self.assertEqual(self.client.post("/api/repositories/upload", content=b"not-zip").status_code, 400)
        self.assertEqual(self.client.post("/api/repositories/import", json={"path": "/"}).status_code, 400)

    def test_upload_enforces_stream_limit_without_content_length(self):
        with patch("roundtable.knowledge_api.MAX_UPLOAD_BYTES", 10):
            response = self.client.post("/api/repositories/upload", content=iter([b"123456", b"abcdef"]))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.store.list(), [])


if __name__ == "__main__":
    unittest.main()
