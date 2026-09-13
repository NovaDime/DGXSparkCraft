import json
import tempfile
import unittest
from pathlib import Path

from roundtable.config import Settings
from scripts.export_openclaw import export_bundle
from tests.test_engine import make_skills


class ExportTests(unittest.TestCase):
    models = {"planner_model": "cloud-provider/planner-model", "local_model": "spark-local/local-model"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_skills(self.root / "skills")
        self.settings = Settings(skills_dir=self.root / "skills", openclaw_token="never-export-this")

    def tearDown(self):
        self.tmp.cleanup()

    def test_portable_bundle_preserves_roles_and_never_exports_credentials(self):
        output = self.root / "bundle"
        result = export_bundle(output, "/home/demo/roundtable", self.settings, **self.models)
        self.assertFalse(result["installed"])
        self.assertEqual(len(result["agents"]), 5)
        config = json.loads((output / "openclaw.fragment.json").read_text(encoding="utf-8"))
        self.assertEqual(config["agents"]["ownership"], "explicit")
        self.assertEqual(config["agents"]["entries"]["host"]["workspace"], "/home/demo/roundtable/workspaces/host")
        for agent_id, entry in config["agents"]["entries"].items():
            expected = self.models["planner_model"] if agent_id == "planner" else self.models["local_model"]
            self.assertEqual(entry["model"], {"primary": expected, "fallbacks": []})
            self.assertEqual(entry["utilityModel"], expected)
            self.assertEqual(entry["tools"], {"profile": "minimal", "deny": ["*"]})
        self.assertTrue(config["gateway"]["http"]["endpoints"]["responses"]["enabled"])
        self.assertTrue((output / "workspaces/host/skills/roundtable-host/SKILL.md").exists())
        for path in output.rglob("*"):
            if path.is_file():
                self.assertNotIn("never-export-this", path.read_text(encoding="utf-8"))

    def test_missing_or_ambiguous_model_routes_fail_before_writing(self):
        output = self.root / "bundle"
        invalid_routes = ({}, {"planner_model": "cloud/model"},
                          {"planner_model": "same/planner", "local_model": "same/local"},
                          {"planner_model": "cloud/model", "local_model": "not-a-ref"},
                          {"planner_model": "cloud/model", "local_model": "spark-local/model with spaces"})
        for routes in invalid_routes:
            with self.subTest(routes=routes), self.assertRaises(ValueError):
                export_bundle(output, "/home/demo/roundtable", self.settings, **routes)
            self.assertFalse(output.exists())

    def test_existing_files_are_never_overwritten(self):
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "important.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            export_bundle(output, "/home/demo/roundtable", self.settings, **self.models)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_rejects_recursive_destination_and_bad_target(self):
        with self.assertRaises(ValueError):
            export_bundle(self.root / "skills/bundle", "/home/demo/project", self.settings, **self.models)
        for invalid in ("relative", "/", "/home/../etc"):
            with self.assertRaises(ValueError):
                export_bundle(self.root / "bundle", invalid, self.settings, **self.models)

    def test_agent_ids_are_distinct(self):
        with self.assertRaises(ValueError):
            Settings(agent_ids={role: "main" for role in ("host", "planner", "balance", "engineer", "reviewer")})
