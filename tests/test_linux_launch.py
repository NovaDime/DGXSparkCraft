import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import linux_studio as launcher

class LauncherTests(unittest.TestCase):
    def test_existing_studio_opens_browser(self):
        with patch.object(launcher, 'processes', return_value={'studio':[42]}), patch.object(launcher, 'health', return_value=True), patch.object(launcher, 'open_studio') as browser, patch.object(launcher, 'ensure_dependencies') as deps:
            launcher.start()
            deps.assert_called_once()
            browser.assert_called_once()

    def test_other_directory_sparkcraft_opens_without_starting(self):
        with patch.object(launcher, 'processes', return_value={'studio':[]}), patch.object(launcher, 'health', return_value=True), patch.object(launcher, 'existing_studio_root', return_value=Path('/another/SparkCraft')), patch.object(launcher, 'open_studio') as browser, patch.object(launcher, 'launch') as launch, patch.object(launcher.subprocess, 'run') as delegate:
            launcher.start()
            browser.assert_not_called()
            launch.assert_not_called()
            self.assertIn('/another/SparkCraft/scripts/linux_studio.py', delegate.call_args.args[0])

    def test_unidentified_service_is_not_adopted(self):
        with patch.object(launcher, 'processes', return_value={'studio':[]}), patch.object(launcher, 'health', return_value=True), patch.object(launcher, 'existing_studio_root', return_value=None), patch.object(launcher, 'open_studio') as browser:
            with self.assertRaises(RuntimeError): launcher.start()
            browser.assert_not_called()

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

    def test_fresh_directory_hands_off_to_installer(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(launcher, 'PYTHON', Path(folder)/'missing'), patch.object(launcher, 'processes', return_value={'studio':[]}), patch.object(launcher, 'health', return_value=False), patch.object(launcher.os, 'execv', side_effect=SystemExit) as execute:
            with self.assertRaises(SystemExit): launcher.start(browser=False)
            self.assertIn('--no-browser',execute.call_args.args[1])
            self.assertTrue(any('deploy_spark.py' in x for x in execute.call_args.args[1]))

    def test_loading_managed_model_waits_without_creating_container(self):
        import json
        from types import SimpleNamespace
        from scripts import deploy_spark as deploy
        item={'Config':{'Labels':{'ai.sparkcraft.managed':'nemotron'},'Cmd':['--model',deploy.MODEL]},'State':{'Running':True}}
        with patch.object(deploy,'available_model',side_effect=[None,deploy.ALIAS]), patch.object(deploy.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps([item]))), patch.object(deploy,'run') as command:
            self.assertEqual(deploy.provision_model(10),deploy.ALIAS)
            command.assert_not_called()

    def test_known_existing_model_reuses_original_cache(self):
        import json
        from types import SimpleNamespace
        from scripts import deploy_spark as deploy
        item={'Config':{'Image':deploy.IMAGE,'Cmd':['--model',deploy.MODEL]},'HostConfig':{'PortBindings':{'8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8000'}]}},'State':{'Running':False}}
        with patch.object(deploy,'available_model',side_effect=[None,deploy.ALIAS]), patch.object(deploy.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps([item]))), patch.object(deploy,'run',return_value=SimpleNamespace(stdout='')) as command, patch.object(deploy.socket,'socket') as sock:
            sock.return_value.__enter__.return_value.connect_ex.return_value=1
            self.assertEqual(deploy.provision_model(10),deploy.ALIAS)
            self.assertIn(unittest.mock.call(['docker','start','nemotron-3.5-lightning']),command.call_args_list)
            self.assertFalse(any('run' in call.args[0] for call in command.call_args_list))
