import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from roundtable.app import create_app
from roundtable.art_models import ArtConnection
from roundtable.config import Settings
from roundtable.export_safety import check_export
from roundtable.knowledge import KnowledgeStore
from tests import test_delivery as delivery_fixture
ProductionProvider = delivery_fixture.ProductionProvider
PLAN = delivery_fixture.PLAN
from tests.test_engine import ScriptedProvider

class WorkflowTests(unittest.TestCase):
    def test_multimodal_private_configuration_and_export_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); settings=Settings(data_dir=root)
            c=ArtConnection(root)
            secret='private-art-fixture-credential'
            result=c.save({'base_url':'https://images.example/v1','model':'image-model','protocol':'openai_images','api_key':secret})
            self.assertTrue(result['configured']);self.assertFalse(result['ready'])
            self.assertNotIn(secret,json.dumps(result))
            self.assertEqual(c.path.stat().st_mode & 0o777,0o600)
            c.save({'base_url':'https://images.example/v1','model':'image-model-2','protocol':'openai_images','api_key':''})
            self.assertEqual(c.read()['api_key'],secret)
            with self.assertRaises(ValueError):check_export(settings,[('report '+secret).encode()])
            with self.assertRaises(ValueError):c.save({'base_url':'https://user:pass@images.example/v1','model':'x','protocol':'openai_images','api_key':secret})

    def test_art_requirement_cannot_silently_disappear_into_finished_package(self):
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),ProductionProvider())) as client:
            helper=delivery_fixture.DeliveryTests();mid=helper.seed(client)
            item=helper.wait(client,client.post(f'/api/meetings/{mid}/delivery').json()['id'])
            art={'id':'glow','kind':'sequence','description':'奖励光效逐渐扩散','trigger':'获得奖励时','frames':9}
            result=client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':1,'confirmed':True,'plan':{**PLAN,'art_assets':[art]}})
            self.assertEqual(result.status_code,409)
            saved=client.get(f"/api/deliveries/{item['id']}").json()
            self.assertIsNone(saved['approval']);self.assertIsNone(saved['code_job_id'])

    def test_continue_discussion_keeps_parent_and_requires_new_approval(self):
        provider=ScriptedProvider()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),simulation_delay_seconds=0),provider)) as client:
            parent=client.post('/api/meetings',json={'topic':'设计矿石采集奖励'}).json()
            import time
            for _ in range(100):
                parent=client.get('/api/meetings/'+parent['id']).json()
                if parent['status']=='completed':break
                time.sleep(.01)
            self.assertEqual(parent['status'],'completed')
            child=client.post('/api/meetings',json={'topic':parent['topic'],'parent_meeting_id':parent['id'],'revision_notes':'减少奖励并取消特殊贴图'}).json()
            self.assertNotEqual(parent['id'],child['id'])
            self.assertEqual(child['parent_proposal'],parent['proposal'])
            self.assertEqual(child['revision_notes'],'减少奖励并取消特殊贴图')
            self.assertIsNone(client.get('/api/meetings/'+child['id']+'/delivery').json())
            self.assertEqual(client.post('/api/meetings',json={'topic':'继续设计采集奖励','parent_meeting_id':'0'*32,'revision_notes':'减少奖励'}).status_code,400)

    def test_library_search_returns_sources_across_repositories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);k=KnowledgeStore(root/'knowledge')
            try:
                for n in ['a','b']:
                    folder=root/n;folder.mkdir();(folder/'cooldown.py').write_text('cooldown_seconds = 12\n')
                    k.import_path(folder,n)
                hits=k.search_all('cooldown_seconds')
                self.assertEqual({x['repository_name'] for x in hits},{'a','b'})
                self.assertTrue(all('repository_revision' in x for x in hits))
            finally:k.close()
