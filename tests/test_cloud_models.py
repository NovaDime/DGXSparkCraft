import json
import tempfile
import unittest
from pathlib import Path
import httpx
from roundtable.cloud_models import CloudModels, CloudError

class CloudTests(unittest.IsolatedAsyncioTestCase):
    async def test_secret_storage_request_and_redacted_public_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CloudModels(Path(tmp))
            key = store.add({'name':'Cloud test','base_url':'https://cloud.example/v1','model':'text-model','api_key':'test-private-credential'})
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('test-private-credential',json.dumps(store.public()))
            def handler(request):
                self.assertEqual(str(request.url),'https://cloud.example/v1/chat/completions')
                self.assertEqual(request.headers['Authorization'],'Bearer test-private-credential')
                self.assertNotIn('test-private-credential',request.content.decode())
                return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'hello test-private-credential'}}],'usage':{'prompt_tokens':4,'completion_tokens':3}})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                text,usage=await store.generate(key,instructions='instruction',prompt='hello',client=client)
            self.assertNotIn('test-private-credential',text)
            self.assertEqual(usage['input_tokens'],4)

    async def test_errors_never_echo_upstream_credentials_and_incomplete_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CloudModels(Path(tmp)); key=store.add({'name':'test','base_url':'https://cloud.example/v1','model':'model','api_key':'private-secret'})
            for response in [httpx.Response(401,text='private-secret'),httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'partial'}}]})]:
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
                    with self.assertRaises(CloudError) as caught: await store.generate(key,instructions='a',prompt='b',client=client)
                self.assertNotIn('private-secret',str(caught.exception))
            for url in ['http://cloud.example/v1','https://u:p@cloud.example/v1','https://cloud.example/v1?key=secret']:
                with self.assertRaises(CloudError): store.add({'name':'test','base_url':url,'model':'model','api_key':'private-secret'})
