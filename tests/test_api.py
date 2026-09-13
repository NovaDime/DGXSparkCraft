import json
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from roundtable.app import DataDirectoryLock, create_app
from roundtable.config import Settings, read_env
from tests.test_engine import ScriptedProvider, make_skills


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_skills(self.root / "skills")
        self.settings = Settings(data_dir=self.root, skills_dir=self.root / "skills", openclaw_token="do-not-expose-token")
        self.client_context = TestClient(create_app(self.settings, ScriptedProvider()))
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_metadata_never_exposes_credentials(self):
        response = self.client.get("/api/meta")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("do-not-expose-token", response.text)
        self.assertEqual(len(response.json()["roles"]), 5)
        self.assertEqual(response.json()["limits"],
                         {"max_rounds_min": 3, "max_rounds_default": 3, "max_rounds_max": 4})

    def test_create_detail_and_export(self):
        response = self.client.post("/api/meetings", json={"topic": "日常委托玩法评审"})
        self.assertEqual(response.status_code, 201)
        meeting_id = response.json()["id"]
        for _ in range(100):
            item = self.client.get(f"/api/meetings/{meeting_id}").json()
            if item["status"] == "completed":
                break
            time.sleep(0.005)
        self.assertEqual(item["status"], "completed")
        self.assertEqual(item["current_round"], 3)
        self.assertTrue(item["include_reviewer"])
        self.assertEqual(len(item["turns"]), 16)
        markdown = self.client.get(f"/api/meetings/{meeting_id}/export?format=markdown")
        self.assertEqual(markdown.status_code, 200)
        self.assertIn("规则模拟", markdown.text)
        self.assertIn("日常委托", markdown.text)
        self.assertIn("attachment", markdown.headers["content-disposition"])
        snapshot = self.client.get(f"/api/meetings/{meeting_id}/export?format=json")
        self.assertEqual(snapshot.json()["id"], meeting_id)
        self.assertEqual(self.client.get(f"/api/meetings/{meeting_id}/export?format=html").status_code, 422)

    def test_validation(self):
        for invalid in ({"topic": "   "}, {"topic": "有效的测试议题", "max_rounds": 2},
                        {"topic": "有效的测试议题", "max_rounds": 5},
                        {"topic": "有效的测试议题", "include_reviewer": "false"},
                        {"topic": "有效的测试议题", "include_reviewer": False},
                        {"topic": "有效的测试议题", "include_reviewer": True},
                        {"topic": "有效的测试议题", "provider_mode": "openclaw"}):
            self.assertEqual(self.client.post("/api/meetings", json=invalid).status_code, 422)

    def test_four_round_limit_is_accepted(self):
        response = self.client.post("/api/meetings", json={"topic": "四轮上限验证", "max_rounds": 4})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["max_rounds"], 4)

    def test_page_has_only_three_and_four_round_choices(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<option value="3" selected>', response.text)
        self.assertIn('<option value="4">', response.text)
        self.assertNotIn('id="include-reviewer"', response.text)

    def test_missing_meeting_and_skill(self):
        self.assertEqual(self.client.get("/api/meetings/missing").status_code, 404)
        self.assertEqual(self.client.post("/api/meetings/missing/cancel").status_code, 404)
        self.assertEqual(self.client.get("/api/skills/not-a-skill").status_code, 404)

    def test_cross_origin_and_untrusted_host_rejected(self):
        response = self.client.post("/api/meetings", json={"topic": "跨站请求不能发起会议"}, headers={"origin": "https://outside.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/health", headers={"host": "outside.example"}).status_code, 400)

    def test_second_worker_cannot_drive_same_database(self):
        with self.assertRaises(RuntimeError):
            DataDirectoryLock(self.root)

    def test_config_and_literal_env(self):
        with self.assertRaises(ValueError):
            Settings(provider_mode="bad")
        with self.assertRaises(ValueError):
            Settings(openclaw_base_url="http://user:secret@localhost:18789")
        with self.assertRaises(ValueError):
            Settings(openclaw_base_url="http://localhost?token=secret")
        env = self.root / "literal.env"
        env.write_text('KEY="literal $(not-executed)"\n', encoding="utf-8")
        self.assertEqual(read_env(env)["KEY"], "literal $(not-executed)")


if __name__ == "__main__":
    unittest.main()
