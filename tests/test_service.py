"""Actual Windows background-process checks using isolated databases and ports."""
import json
from contextlib import closing
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import httpx

from scripts.service import ROOT, ProcessHandle, process_matches


@unittest.skipUnless(os.name == "nt", "Windows lifecycle manager")
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="roundtable-service-test-")
        self.directory = Path(self.temporary.name)
        self.runtime = self.directory / "runtime"
        self.environment = {**os.environ, "ROUNDTABLE_PROVIDER": "simulation",
                            "ROUNDTABLE_DATA_DIR": str(self.directory / "data"),
                            "ROUNDTABLE_SIMULATION_DELAY": "1", "PYTHONUTF8": "1"}
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]

    def command(self, action, *args, success=True):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/service.py"), action,
                    "--runtime-dir", str(self.runtime), *args], env=self.environment,
                    capture_output=True, encoding="utf-8", timeout=40)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def start(self):
        return self.command("start", "--port", str(self.port), "--no-browser")

    def state(self):
        return json.loads(self.command("status", "--json").stdout)

    def saved_meeting(self, identifier):
        with closing(sqlite3.connect(self.directory / "data/meetings.sqlite3")) as connection:
            return json.loads(connection.execute("SELECT payload FROM meetings WHERE id=?", (identifier,)).fetchone()[0])

    def tearDown(self):
        try:
            self.command("stop", "--timeout", "1")
        finally:
            self.temporary.cleanup()

    def test_duplicate_start_graceful_stop_preserves_active_meeting_and_restarts(self):
        self.start()
        original = self.state()
        self.assertTrue(original["running"])
        self.assertEqual(original["health"]["provider_mode"], "simulation")
        self.start()
        self.assertEqual(self.state()["pid"], original["pid"])
        with httpx.Client(base_url=original["url"], trust_env=False) as client:
            response = client.post("/api/meetings", json={"topic": "验收服务关闭时保存会议记录"})
            response.raise_for_status()
            identifier = response.json()["id"]
        self.command("stop")
        stopped = self.state()
        self.assertFalse(stopped["running"])
        self.assertEqual(stopped["phase"], "stopped")
        self.assertEqual(self.saved_meeting(identifier)["status"], "interrupted")
        launcher = json.loads((self.runtime / "launcher.json").read_text(encoding="utf-8"))
        self.assertFalse(process_matches(launcher))
        self.start()
        self.assertTrue(self.state()["running"])
        self.assertEqual(self.saved_meeting(identifier)["status"], "interrupted")

    def test_force_stop_releases_process_and_restart_recovers_record(self):
        self.start()
        before = self.state()
        with httpx.Client(base_url=before["url"], trust_env=False) as client:
            response = client.post("/api/meetings", json={"topic": "验收强制关闭后恢复已保存的会议"})
            response.raise_for_status()
            identifier = response.json()["id"]
        self.command("stop", "--timeout", "0")
        self.assertFalse(self.state()["running"])
        self.assertEqual(self.state()["phase"], "forced_stop")
        launcher = json.loads((self.runtime / "launcher.json").read_text(encoding="utf-8"))
        self.assertFalse(process_matches(launcher))
        self.start()
        self.assertEqual(self.saved_meeting(identifier)["status"], "interrupted")

    def test_occupied_port_is_not_taken_over(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", self.port))
            listener.listen()
            result = self.command("start", "--port", str(self.port), "--no-browser", success=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("已被占用", result.stderr)
            self.assertFalse((self.runtime / "service.json").exists())

    def test_identity_guard_and_foreign_project_are_rejected(self):
        with ProcessHandle(os.getpid()) as process:
            state = {"project_root": str(ROOT), "pid": os.getpid(), "process_created": process.identity()}
        self.assertTrue(process_matches(state))
        self.assertFalse(process_matches({**state, "process_created": "stale-process"}))
        self.assertFalse(process_matches({**state, "project_root": str(self.directory)}))

    def test_powershell_wrapper_works_outside_project_with_arguments(self):
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "scripts/manage.ps1"), "status", "--json", "--runtime-dir", str(self.runtime)],
                    env={**self.environment, "ROUNDTABLE_PYTHON": sys.executable}, cwd=self.directory,
                    capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["running"])


if __name__ == "__main__":
    unittest.main()
