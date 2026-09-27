import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path
import httpx
from roundtable.guide_snapshot import sync_guide, guide_paths

class GuideSnapshotTests(unittest.TestCase):
    def test_scope_and_truncated_directory(self):
        with self.assertRaises(ValueError):
            guide_paths({'truncated': True})
        with self.assertRaises(ValueError):
            guide_paths({'tree':[{'type':'blob','path':'mcguide/../bad.md'}]})
        self.assertEqual(guide_paths({'tree':[
            {'type':'blob','path':'mcguide/a.md'}, {'type':'blob','path':'mcguide/a.png'},
            {'type':'blob','path':'other/b.md'}]}), ['mcguide/a.md'])

    def test_full_text_provenance_and_resumable_hash(self):
        async def run():
            requests=[]
            def handler(request):
                requests.append(str(request.url))
                if 'api.github.com' in str(request.url):
                    return httpx.Response(200,json={'tree':[{'type':'blob','path':'mcguide/a.md'}]})
                return httpx.Response(200,text='# 完整正文\n'+'测试内容'*3000)
            with tempfile.TemporaryDirectory() as tmp:
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    folder=Path(tmp)/'guide-source'
                    first=await sync_guide(folder,client)
                    body=(folder/'guide/a.md').read_text()
                    self.assertTrue(body.endswith('测试内容'*3000))
                    self.assertIn('原始官方链接',body)
                    self.assertEqual(first['document_count'],1)
                    self.assertEqual(first['failures'],[])
                    await sync_guide(folder,client)
                    self.assertEqual(len(requests),3)  # second sync only fetches directory
                    (folder/'guide/a.md').write_text('corrupt')
                    await sync_guide(folder,client)
                    self.assertEqual(len(requests),5)
        asyncio.run(run())
