import asyncio
import io
import json
import math
import struct
import tempfile
import time
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from roundtable.app import create_app
from roundtable.audio_generation import StepAudio, AudioError
from roundtable.config import Settings
from roundtable.development import stamp


ASSET = {"id":"welcome", "kind":"npc", "text":"欢迎来到矿洞", "voice":"温暖低沉的成年男性", "direction":"轻松友好，干声，无配乐", "trigger":"与向导 NPC 交互时一次"}
PLAN = {"title":"矿洞向导", "target":"中国版基岩 1.24", "code_task":"实现向导交互与欢迎配音", "assets":[ASSET], "required_resources":[]}


def wav_fixture():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
        output.writeframes(b"".join(struct.pack('<h', int(8000 * math.sin(2 * math.pi * 440 * t / 24000))) for t in range(2400)))
    return buffer.getvalue()


class ProductionProvider:
    def __init__(self): self.calls = []
    async def complete_text(self, **args):
        self.calls.append(args)
        scope = args['scope']
        if scope.endswith(':plan'):
            result = {**PLAN, "assets":[]}
        elif scope.endswith(':art-plan'):
            result = {'art_assets':[]}
        elif scope.endswith(':audio-plan'):
            result = {"assets":[ASSET]}
        elif 'review' in scope:
            result = {"approved":True, "summary":"测试用确定性独立审查", "issues":[]}
        else:
            result = {"summary":"测试用入口与声音引用", "files":[
                {"path":"behavior_pack/SparkCraftScripts/__init__.py", "content":""},
                {"path":"behavior_pack/SparkCraftScripts/modMain.py", "content":
                 'from mod.common.mod import Mod\n@Mod.Binding(name="SparkCraft", version="1.0")\nclass Entry(object):\n    @Mod.Init()\n    def init(self):\n        self.sound = "sparkcraft.welcome"\n'}],
                "assumptions":[],"api_evidence":[]}
        return json.dumps(result, ensure_ascii=False), {}
    async def aclose(self): pass


class DeliveryTests(unittest.TestCase):
    def test_conversion_failure_retry_reuses_paid_wav(self):
        provider = ProductionProvider()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),provider)) as client:
            mid=self.seed(client); item=self.wait(client,client.post(f'/api/meetings/{mid}/delivery').json()['id'])
            client.app.state.delivery.audio.save({'api_key':'test-audio-private-key','endpoint':'https://api.stepfun.com/v1/audio/generate','model':'stepaudio-3-gen-preview'})
            async def generate(*args, **kwargs): return wav_fixture(), StepAudio.validate_wav(wav_fixture())
            with patch.object(StepAudio,'generate',side_effect=generate) as generated:
                with patch.object(StepAudio,'game_audio',side_effect=AudioError('local conversion failed')):
                    client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':1,'confirmed':True,'plan':PLAN})
                    self.assertEqual(self.wait(client,item['id'])['status'],'blocked')
                client.post(f"/api/deliveries/{item['id']}/retry",json={'confirmed':True})
                self.assertEqual(self.wait(client,item['id'])['status'],'packaged')
                self.assertEqual(generated.call_count,1, '本地转换失败不能导致重新购买音频生成')

    def test_report_secret_is_rejected_before_package_publication(self):
        from roundtable.delivery import digest
        provider = ProductionProvider()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp), provider_mode='openclaw'), provider)) as client:
            engine = client.app.state.delivery
            secret = 'test-secret-in-review-report'
            engine.audio.save({'api_key':secret,'endpoint':'https://api.stepfun.com/v1/audio/generate','model':'stepaudio-3-gen-preview'})
            root = Path(tmp)/'package'; root.mkdir()
            item = {'id':'a'*32,'plan':PLAN,'approval':{'plan_hash':digest(PLAN)},'checks':[],
                    'review':{'approved':True,'summary':secret,'issues':[]}}
            with self.assertRaises(ValueError):
                engine.package(item, {'behavior_pack/test.py':b'x = 1'}, root)
            self.assertFalse((root/'delivery.zip').exists())

    def test_duplicate_plan_keys_get_one_bounded_repair_before_human_review(self):
        class DuplicateFirst(ProductionProvider):
            async def complete_text(self, **args):
                if not self.calls:
                    self.calls.append(args)
                    return '{"code_task":"first","code_task":"second"}', {}
                return await super().complete_text(**args)
        provider = DuplicateFirst()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),provider)) as client:
            mid = self.seed(client)
            item = self.wait(client, client.post(f'/api/meetings/{mid}/delivery').json()['id'])
            self.assertEqual(item['status'], 'awaiting_approval', item.get('error'))
            self.assertIsNone(item['approval'])
            self.assertIsNone(item['code_job_id'])
            self.assertEqual(item['plan']['assets'][0]['id'], 'welcome')

    def seed(self, client):
        meeting = {"id":"a"*32, "created_at":stamp(), "status":"completed", "proposal":"NPC 交互播放欢迎音效", "provider_mode":"openclaw"}
        client.app.state.store.save(meeting)
        return meeting['id']

    def wait(self, client, identifier):
        for _ in range(300):
            data=client.get('/api/deliveries/'+identifier).json()
            if data['status'] not in {'planning','queued','running'}: return data
            time.sleep(.01)
        self.fail('delivery did not finish')

    def test_human_gate_dedup_sound_execution_and_clean_package(self):
        provider = ProductionProvider()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),provider)) as client:
            meeting_id=self.seed(client)
            draft=client.post(f'/api/meetings/{meeting_id}/delivery').json()
            item=self.wait(client,draft['id'])
            self.assertEqual(item['status'],'awaiting_approval',item)
            self.assertEqual(len(provider.calls),3)
            self.assertFalse(item['code_job_id']); self.assertIsNone(item['approval'])
            self.assertEqual(client.post(f'/api/meetings/{meeting_id}/delivery').json()['id'],item['id'])
            self.assertEqual(client.post('/api/development/jobs',json={'task':'直接绕过审核执行','meeting_id':meeting_id}).status_code,409)
            self.assertEqual(client.get(f"/api/deliveries/{item['id']}/download").status_code,409)
            self.assertEqual(client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':2,'confirmed':True,'plan':PLAN}).status_code,409)
            secret='sk-' + 'test-never-export-this-secret'
            client.post('/api/audio/config',json={'api_key':secret,'endpoint':'https://api.stepfun.com/v1/audio/generate','model':'stepaudio-3-gen-preview'})
            async def generate(*args, **kwargs): return wav_fixture(), StepAudio.validate_wav(wav_fixture())
            with patch.object(StepAudio,'generate',side_effect=generate) as audio:
                self.assertEqual(client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':1,'confirmed':True,'plan':PLAN}).status_code,200)
                self.assertEqual(client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':1,'confirmed':True,'plan':PLAN}).status_code,409)
                result=self.wait(client,item['id'])
                self.assertEqual(result['status'],'packaged',result)
                self.assertEqual(audio.call_count,1)
            download=client.get(result['download_url'])
            with zipfile.ZipFile(io.BytesIO(download.content)) as z:
                self.assertEqual(set(z.namelist()),{'addon.zip','README.txt','CHECKS.json'})
                self.assertNotIn(secret,z.read('CHECKS.json').decode())
                self.assertFalse(json.loads(z.read('CHECKS.json'))['game_verified'])
                with zipfile.ZipFile(io.BytesIO(z.read('addon.zip'))) as addon:
                    self.assertTrue(any(p.endswith('/welcome.ogg') for p in addon.namelist()))
                    for p in addon.namelist():
                        self.assertNotIn('private',p)
                        if not p.endswith('.ogg'): self.assertNotIn(secret.encode(),addon.read(p))
            self.assertEqual(client.get(result['sounds']['welcome']['url']).headers['content-type'],'audio/ogg')

    def test_missing_key_blocks_without_coding_or_audio_and_revise_revokes_approval(self):
        provider=ProductionProvider()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),provider)) as client:
            mid=self.seed(client)
            draft=client.post(f'/api/meetings/{mid}/delivery').json(); item=self.wait(client,draft['id'])
            response=client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':1,'confirmed':True,'plan':PLAN})
            self.assertEqual(response.status_code,200)
            blocked=self.wait(client,item['id']); self.assertEqual(blocked['status'],'blocked'); self.assertEqual(len(provider.calls),3)
            self.assertEqual(client.post(f"/api/deliveries/{item['id']}/retry",json={}).status_code,400)
            revised=client.post(f"/api/deliveries/{item['id']}/revise",json={'notes':'将欢迎语改为更简短的版本'}).json()
            self.assertIsNone(revised['plan'], '旧任务单不能冒充新修订稿进入审核表单')
            revised=self.wait(client,revised['id'])
            self.assertIsNone(revised['approval']); self.assertEqual(revised['revision'],2)
            self.assertEqual(revised['status'],'awaiting_approval')
            self.assertEqual(client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':1,'confirmed':True,'plan':PLAN}).status_code,409)

    def test_unresolved_resources_and_missing_entry_cannot_package(self):
        provider=ProductionProvider()
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(data_dir=Path(tmp),provider_mode='openclaw'),provider)) as client:
            mid=self.seed(client); item=self.wait(client,client.post(f'/api/meetings/{mid}/delivery').json()['id'])
            self.assertEqual(client.post(f"/api/deliveries/{item['id']}/approve",json={'revision':1,'confirmed':True,'plan':{**PLAN,'required_resources':['新的 NPC 贴图']}}).status_code,409)
            checks=client.app.state.delivery.check_files(item,{'behavior_pack/logic.py':b'answer = 1'})
            self.assertTrue(any(c['level']=='error' for c in checks))


class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_payload_wav_to_ogg_and_secret_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio=StepAudio(Path(tmp)); secret='sk-' + 'test-audio-secret-no-export'
            audio.save({'api_key':secret,'endpoint':'https://api.stepfun.com/v1/audio/generate','model':'stepaudio-3-gen-preview'})
            self.assertEqual(audio.path.stat().st_mode & 0o777,0o600)
            self.assertNotIn(secret,json.dumps(audio.public()))
            def respond(request):
                value=json.loads(request.content)
                self.assertEqual(value['task'],'text_to_audio'); self.assertEqual(value['model'],'stepaudio-3-gen-preview')
                self.assertEqual(value['roles'][0]['description'],ASSET['voice']); self.assertEqual(value['scripts'][0]['text'],ASSET['text'])
                self.assertEqual(request.headers['Authorization'],'Bearer '+secret)
                return httpx.Response(200,content=wav_fixture())
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                wav,meta=await audio.generate(ASSET,audio.public(),client)
            self.assertEqual(meta['sample_rate'],24000)
            ogg=audio.game_audio(wav); self.assertTrue(ogg.startswith(b'OggS'))
            calls=[]
            def denied(req): calls.append(req); return httpx.Response(401,text=secret)
            async with httpx.AsyncClient(transport=httpx.MockTransport(denied)) as client:
                with self.assertRaises(AudioError) as raised: await audio.generate(ASSET,audio.public(),client)
            self.assertNotIn(secret,str(raised.exception)); self.assertEqual(len(calls),1)
            with self.assertRaises(AudioError): audio.validate_wav(b'not audio')
