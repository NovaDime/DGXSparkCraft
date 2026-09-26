import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertEqual(len(result["agents"]), 6)
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

    def test_dry_run_has_no_writes_and_matches_exported_plan(self):
        output = self.root / "new-parent" / "bundle"
        with patch("socket.socket", side_effect=AssertionError("dry-run must not use the network")):
            result = export_bundle(output, "/home/demo/roundtable", self.settings, dry_run=True, **self.models)
        self.assertFalse(output.parent.exists())
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["installed"])
        self.assertFalse(result["network_contacted"])
        self.assertEqual(len(result["agents"]), 6)
        self.assertEqual(result["validation"]["signature"], "unsigned")
        self.assertEqual(result["validation"]["role_inference"], "not_run")
        self.assertNotIn("never-export-this", json.dumps(result))
        export_bundle(output, "/home/demo/roundtable", self.settings, **self.models)
        plan = json.loads((output / "deployment-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan, {key: value for key, value in result.items() if key not in {"output", "dry_run"}})

    def test_dry_run_rejects_invalid_routes_and_existing_output(self):
        output = self.root / "bundle"
        with self.assertRaises(ValueError):
            export_bundle(output, "/home/demo/roundtable", self.settings,
                          planner_model="cloud/one", local_model="cloud/two", dry_run=True)
        self.assertFalse(output.exists())
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            export_bundle(output, "/home/demo/roundtable", self.settings, dry_run=True, **self.models)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def _dry_run_cli(self, env_file, overrides=None):
        project = Path(__file__).resolve().parents[1]
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("ROUNDTABLE_", "OPENCLAW_"))}
        environment.update(overrides or {})
        return subprocess.run(
            [sys.executable, "-B", str(project / "scripts/export_openclaw.py"),
             "--env-file", str(env_file), "--output", str(self.root / "cli-bundle"),
             "--target-root", "/home/demo/roundtable", "--planner-model", self.models["planner_model"],
             "--local-model", self.models["local_model"], "--dry-run"],
            cwd=project, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def test_cli_uses_staged_env_and_reports_effective_config(self):
        staged = self.root / "generated.env"
        content = ("ROUNDTABLE_PROVIDER=openclaw\nOPENCLAW_BASE_URL=http://127.0.0.1:19999\n"
                   "OPENCLAW_AGENT_HOST=staged_host\nROUNDTABLE_REQUEST_TIMEOUT=41\n"
                   "OPENCLAW_TOKEN=staged-canary-secret\n")
        staged.write_text(content, encoding="utf-8")
        result = self._dry_run_cli(staged, {"ROUNDTABLE_REQUEST_TIMEOUT": "52"})
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["roundtable"]["provider_mode"], "openclaw")
        self.assertEqual(plan["roundtable"]["gateway_url"], "http://127.0.0.1:19999")
        self.assertEqual(plan["roundtable"]["request_timeout_seconds"], 52)
        self.assertIn("staged_host", plan["agents"])
        self.assertNotIn("staged-canary-secret", result.stdout + result.stderr)
        self.assertEqual(staged.read_text(encoding="utf-8"), content)
        self.assertFalse((self.root / "cli-bundle").exists())

    def test_cli_rejects_missing_staged_env(self):
        result = self._dry_run_cli(self.root / "missing.env")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.root / "cli-bundle").exists())

    def test_real_bundle_has_skill_cards_but_no_deployment_agent(self):
        project = Path(__file__).resolve().parents[1]
        output = self.root / "real-bundle"
        settings = Settings(skills_dir=project / "skills")
        result = export_bundle(output, "/home/demo/roundtable", settings, **self.models)
        self.assertEqual(set(result["agents"]), {"host", "planner", "balance", "engineer", "audio", "reviewer"})
        cards = list(output.glob("workspaces/*/skills/*/SKILL_CARD.json"))
        self.assertEqual(len(cards), 6)
        for path in cards:
            card = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.read_bytes(), (project / "skills" / card["skill_id"] / "SKILL_CARD.json").read_bytes())
            self.assertTrue(card["requirements"]["meeting_participant"])
            self.assertEqual(card["trust"]["signature"]["status"], "unsigned")
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))["files"]
        actual = {path.relative_to(output).as_posix() for path in output.rglob("*")
                  if path.is_file() and path.name != "manifest.json"}
        self.assertEqual(set(manifest), actual)
        for name, expected_hash in manifest.items():
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected_hash)

    def test_rejects_recursive_destination_and_bad_target(self):
        with self.assertRaises(ValueError):
            export_bundle(self.root / "skills/bundle", "/home/demo/project", self.settings, **self.models)
        for invalid in ("relative", "/", "/home/../etc"):
            with self.assertRaises(ValueError):
                export_bundle(self.root / "bundle", invalid, self.settings, **self.models)

    def test_agent_ids_are_distinct(self):
        with self.assertRaises(ValueError):
            Settings(agent_ids={role: "main" for role in ("host", "planner", "balance", "engineer", "reviewer")})
