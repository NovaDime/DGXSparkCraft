import asyncio
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from roundtable.app import create_app
from roundtable.config import Settings
from roundtable.development import validate_files
from roundtable.providers import OpenClawProvider, ProviderError
import httpx


class CodingProvider:
    def __init__(self, broken=False, wait=False):
        self.calls = []
        self.broken = broken
        self.wait = wait
    async def complete_text(self, **kwargs):
        self.calls.append(kwargs)
        if self.wait:
            await asyncio.sleep(10)
        if kwargs['agent_id'] == 'coder':
            text = 'def broken(:\n' if self.broken and len(self.calls) == 1 else 'def total(a, b):\n    return a + b\n'
            result = {'summary': '实现加法逻辑', 'files': [{'path': 'logic.py','content': text}], 'assumptions': [], 'api_evidence': []}
        else:
            result = {'approved': True, 'summary': '独立审查完成', 'issues': []}
        return json.dumps(result), {'input_tokens': 10, 'output_tokens': 20}
    async def aclose(self):
        pass


class DevelopmentTests(unittest.TestCase):
    def wait_job(self, client, identifier):
        for _ in range(150):
            job = client.get('/api/development/jobs/' + identifier).json()
            if job['status'] not in {'queued', 'running'}:
                return job
            time.sleep(.01)
        self.fail('job did not finish')

    def test_no_repository_simulation_has_files_and_download(self):
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp)))) as client:
            response = client.post('/api/development/jobs', json={'task': '实现单机冷却组件'})
            self.assertEqual(response.status_code, 201)
            job = self.wait_job(client, response.json()['id'])
            self.assertEqual(job['status'], 'completed', job.get('error'))
            self.assertEqual(job['provider_mode'], 'simulation')
            self.assertEqual(job['metrics']['model_calls'], 0)
            data = client.get(job['download_url'])
            with zipfile.ZipFile(io.BytesIO(data.content)) as z:
                self.assertIn('scripts/cooldown.py', z.namelist())
                self.assertIn('SPARKCRAFT-REPORT.json', z.namelist())
            with patch('roundtable.development.shutil.which', return_value='/bin/code'), patch('roundtable.development.subprocess.Popen') as call:
                self.assertEqual(client.post('/api/development/jobs/' + job['id'] + '/open-vscode').status_code, 200)
                self.assertEqual(call.call_args.args[0], ['/bin/code', '--new-window', job['workspace_path']])

    def test_actual_checks_override_self_approval_then_bounded_repair(self):
        provider = CodingProvider(broken=True)
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp), provider_mode='openclaw', max_context_chars=64000), provider)) as client:
            response = client.post('/api/development/jobs', json={'task': '实现加法逻辑', 'runtime': 'python3', 'max_repairs': 1})
            job = self.wait_job(client, response.json()['id'])
            self.assertEqual(job['status'], 'completed', job.get('error'))
            self.assertEqual(job['metrics']['model_calls'], 4)
            self.assertIn('def broken', provider.calls[2]['prompt'])
            self.assertTrue(any(x['phase'] == 'repair' for x in job['events']))
            self.assertEqual([x['agent_id'] for x in provider.calls], ['coder', 'reviewer', 'coder', 'reviewer'])
            self.assertEqual(len({x['scope'] for x in provider.calls}), 4)

    def test_repair_limit_retains_unresolved_error(self):
        provider = CodingProvider(broken=True)
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp), provider_mode='openclaw'), provider)) as client:
            response = client.post('/api/development/jobs', json={'task': '实现加法逻辑', 'runtime': 'python3', 'max_repairs': 0})
            job = self.wait_job(client, response.json()['id'])
            self.assertEqual(job['status'], 'needs_review')
            self.assertTrue(any(x['level'] == 'error' for x in job['checks']))

    def test_imported_original_untouched_candidate_not_automatically_accepted(self):
        provider = CodingProvider()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            (source / 'logic.py').write_text('def total(a, b):\n    return 0\n')
            with TestClient(create_app(Settings(data_dir=root/'data', provider_mode='openclaw'), provider)) as client:
                repo = client.post('/api/repositories/import', json={'path': str(source)}).json()
                result = client.post('/api/development/jobs', json={'task':'修复 logic total 加法逻辑', 'repository_id':repo['id'], 'runtime':'python3'}).json()
                job = self.wait_job(client, result['id'])
                self.assertEqual(job['status'], 'completed', job.get('error'))
                self.assertIn('return 0', (source/'logic.py').read_text())
                self.assertIn('return a + b', Path(job['workspace_path'], 'logic.py').read_text())
                self.assertIn('-    return 0', job['diff'])
                candidates = client.get('/api/repositories/'+repo['id']+'/feedback').json()
                self.assertFalse(candidates[0]['accepted'])
                self.assertEqual(candidates[0]['id'], job['learning_candidate_id'])

    def test_cancel_and_reject_nonconverged_design(self):
        provider = CodingProvider(wait=True)
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),provider)) as client:
            result = client.post('/api/development/jobs', json={'task':'实现加法逻辑'}).json()
            job_id = result['id']
            self.assertEqual(client.post('/api/development/jobs/'+job_id+'/cancel').json()['status'], 'cancelled')
            self.assertEqual(client.post('/api/development/jobs/'+job_id+'/open-vscode').status_code, 409)
            self.assertEqual(client.post('/api/development/jobs', json={'task':'实现加法逻辑','meeting_id':'0'*32}).status_code,404)

    def test_protocol_failure_uses_bounded_repair(self):
        class WrongFirst(CodingProvider):
            async def complete_text(self, **kwargs):
                if not self.calls:
                    self.calls.append(kwargs)
                    return '{"plan":"will explore"}', {'input_tokens':1,'output_tokens':1}
                return await super().complete_text(**kwargs)
        provider = WrongFirst()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),provider)) as client:
            created = client.post('/api/development/jobs',json={'task':'实现加法逻辑','runtime':'python3','max_repairs':1}).json()
            job = self.wait_job(client,created['id'])
            self.assertEqual(job['status'],'completed',job.get('error'))
            self.assertEqual(job['metrics']['model_calls'],3)
            self.assertTrue(any(e['phase']=='protocol_repair' for e in job['events']))

    def test_paths_and_duplicates(self):
        for name in ['../escape.py','/escape.py','a/../../escape.py','a\\escape.py','a/.env','C:/evil.py','.vscode/tasks.json','a//b.py']:
            with self.assertRaises(ValueError):
                validate_files([{'path':name,'content':'x'}])
        with self.assertRaises(ValueError):
            validate_files([{'path':'a.py','content':'x'},{'path':'A.py','content':'x'}])

    def test_json_request_limit_without_content_length_and_origin(self):
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp)))) as client:
            response = client.post('/api/development/jobs', content=iter([b'x'*40000,b'x'*40000]), headers={'content-type':'application/json'})
            self.assertEqual(response.status_code, 413)
            self.assertEqual(client.post('/api/development/jobs',json={'task':'不允许跨站'},headers={'origin':'https://outside.example'}).status_code,403)


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_or_tool_pending_is_not_a_valid_artifact(self):
        for payload in [ {'status':'incomplete','output':[]}, {'status':'completed','output':[{'type':'function_call'}]},
                         {'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'{}'}]}, {'type':'message','role':'assistant','content':[]}]} ]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=payload))) as client:
                provider = OpenClawProvider(Settings(),client=client)
                with self.assertRaises(ProviderError):
                    await provider.complete_text(prompt='test',agent_id='coder',scope='test')

if __name__ == '__main__':
    unittest.main()
