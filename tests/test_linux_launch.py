import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import linux_studio as launcher

class LauncherTests(unittest.TestCase):
    def test_existing_studio_opens_browser(self):
        with patch.object(launcher, 'processes', return_value={'studio':[42]}), patch.object(launcher, 'health', return_value=True), patch.object(launcher, 'open_studio') as browser:
            launcher.start()
            browser.assert_called_once()

    def test_headless_does_not_open_browser(self):
        with patch.dict('os.environ', {}, clear=True), patch('subprocess.Popen') as spawn:
            launcher.open_studio()
            spawn.assert_not_called()

    def test_deployment_dry_run_has_no_writes(self):
        from scripts import deploy_spark
        with tempfile.TemporaryDirectory() as folder, patch.object(deploy_spark, 'ROOT', Path(folder)), patch.object(deploy_spark, 'run') as run:
            deploy_spark.main(['--dry-run'])
            run.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_model_command_is_loopback_and_pinned(self):
        from scripts import deploy_spark
        command = deploy_spark.model_command()
        self.assertIn('vllm/vllm-openai:v0.27.1', command)
        self.assertIn('127.0.0.1:8000:8000', command)
        self.assertIn('marlin', command)
        self.assertNotIn('--restart', command)

    def test_model_reuse_never_runs_docker(self):
        from scripts import deploy_spark
        with patch.object(deploy_spark, 'available_model', return_value=deploy_spark.ALIAS), patch.object(deploy_spark, 'run') as run:
            self.assertEqual(deploy_spark.provision_model(1), deploy_spark.ALIAS)
            run.assert_not_called()

    def test_relocate_workspaces_preserves_credentials(self):
        import json
        from scripts import setup_local_openclaw as setup
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            config = {'gateway': {'auth': {'token': 'keep'}}, 'agents': {'defaults': {'workspace':'/old/data/openclaw/default-workspace'}, 'entries': {'coder': {'workspace':'/old/data/openclaw/workspaces/coder'}}}}
            (output/'openclaw.json').write_text(json.dumps(config))
            setup.relocate_workspaces(output)
            updated = json.loads((output/'openclaw.json').read_text())
            self.assertEqual(updated['gateway'], config['gateway'])
            self.assertEqual(updated['agents']['entries']['coder']['workspace'], str(output/'workspaces/coder'))
