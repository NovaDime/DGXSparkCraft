import json
import tempfile
import unittest
from pathlib import Path
from roundtable.agent_models import ModelRoutes
from roundtable.config import Settings

class ModelRouteTests(unittest.TestCase):
    def test_public_catalog_persistence_and_allowlist(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'openclaw').mkdir()
            (root/'openclaw/openclaw.json').write_text(json.dumps({
                'models': {'providers': {'local': {'apiKey': 'DO-NOT-EXPOSE-THIS-SECRET', 'models': [{'id':'one','input':['text']},{'id':'two','input':['text']} ]}}},
                'agents': {'defaults': {'model': {'primary':'local/one'}}}
            }))
            settings = Settings(data_dir=root); routes = ModelRoutes(settings)
            snapshot = routes.snapshot()
            routes.set('audio','local/two')
            self.assertEqual(snapshot['audio'],'local/one')
            self.assertEqual(ModelRoutes(settings).snapshot()['audio'],'local/two')
            self.assertNotIn('DO-NOT-EXPOSE',json.dumps(routes.public()))
            with self.assertRaises(ValueError): routes.set('audio','other/unknown')
            with self.assertRaises(ValueError): routes.set('unknown','local/one')
            routes.set('audio','')
            self.assertEqual(routes.snapshot()['audio'],'local/one')
