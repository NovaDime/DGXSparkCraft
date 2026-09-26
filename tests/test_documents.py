import io
import unittest
import zipfile
from roundtable.documents import extract_document, validate_url

class DocumentTests(unittest.TestCase):
    def test_html_drops_scripts(self):
        text = extract_document(b'<h1>API</h1><script>secret()</script><p>SpawnActor</p>', 'doc.html')
        self.assertIn('SpawnActor', text)
        self.assertNotIn('secret', text)

    def test_docx_and_unsupported(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="urn:test"><w:p><w:t>SpawnActor</w:t></w:p></w:document>')
        self.assertIn('SpawnActor', extract_document(data.getvalue(), 'doc.docx'))
        with self.assertRaises(ValueError): extract_document(b'bad', 'binary.exe')

    def test_private_urls_rejected(self):
        for url in ['http://example.com', 'https://127.0.0.1', 'https://user:pass@example.com', 'https://[::1]', 'https://example.com:8000']:
            with self.assertRaises(ValueError): validate_url(url)

from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
from roundtable.app import create_app
from roundtable.config import Settings
from tests.test_engine import ScriptedProvider, make_skills
from unittest.mock import AsyncMock, patch

class DocumentAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        make_skills(root / 'skills')
        self.settings = Settings(data_dir=root, skills_dir=root/'skills', openclaw_token='private-test-token')
        self.app = create_app(self.settings, ScriptedProvider())
        self.context = TestClient(self.app); self.client = self.context.__enter__()
    def tearDown(self):
        self.context.__exit__(None,None,None); self.tmp.cleanup()
    def test_import_game_evidence_and_require_model(self):
        body = dict(game='Godot',version='4',title='Node docs',text='Node is the base class. QueueFree removes a node.',analyze=False)
        r = self.client.post('/api/documents/import',json=body)
        self.assertEqual(r.status_code,200,r.text)
        identifier = r.json()['repository']['id']
        matches = self.client.get(f'/api/repositories/{identifier}/search?q=QueueFree').json()
        self.assertTrue(matches)
        self.assertEqual(self.client.post('/api/documents/import',json={**body,'analyze':True}).status_code,422)
    def test_model_recognition_and_secret_storage(self):
        cloud = self.client.post('/api/cloud-models',json=dict(name='doc model',model='test-model',base_url='https://example.com/v1',api_key='private-doc-key')).json()
        self.assertNotIn('private-doc-key',str(cloud))
        self.assertEqual(self.client.post('/api/documents/model',json={'model':cloud['id']}).status_code,200)
        with patch.object(self.app.state.model_routes.cloud,'generate',AsyncMock(return_value=('{"summary":"QueueFree removes a node; verify version."}',{}))) as call:
            response=self.client.post('/api/documents/import',json=dict(game='Godot',title='Nodes',text='QueueFree removes a node.',analyze=True))
            self.assertEqual(response.status_code,200,response.text)
            self.assertIn('QueueFree',response.json()['analysis']); call.assert_awaited_once()
        self.assertEqual((self.settings.data_dir/'private/cloud-models.json').stat().st_mode & 0o777,0o600)
    def test_history_soft_delete_restore_and_active_guard(self):
        store=self.app.state.store
        item=dict(id='test',topic='Delete test',status='completed',provider_mode='simulation',created_at='today',updated_at='today',current_round=3,max_rounds=3,include_reviewer=True)
        store.save(item)
        self.assertEqual(self.client.post('/api/meetings/test/visibility').status_code,200)
        self.assertEqual(self.client.get('/api/meetings').json(),[])
        self.assertEqual(len(self.client.get('/api/meetings?deleted=true').json()),1)
        self.assertEqual(self.client.post('/api/meetings/test/visibility?deleted=false').status_code,200)
        item['status']='running';store.save(item)
        self.assertEqual(self.client.post('/api/meetings/test/visibility').status_code,409)
        engine=self.app.state.development
        self.client.portal.call(engine.save, dict(id='job',status='completed',task='test'))
        self.assertEqual(self.client.post('/api/development/jobs/job/visibility').status_code,200)
        self.assertEqual(self.client.get('/api/development/jobs').json(),[])
        self.assertIsNotNone(self.client.portal.call(engine.get, 'job'))
        self.assertEqual(self.client.post('/api/development/jobs/job/visibility?deleted=false').status_code,200)
        self.assertEqual(len(self.client.get('/api/development/jobs').json()),1)
        self.client.portal.call(engine.save, dict(id='active',status='running',task='test'))
        self.assertEqual(self.client.post('/api/development/jobs/active/visibility').status_code,409)
