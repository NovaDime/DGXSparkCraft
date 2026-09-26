import tempfile
import unittest
from pathlib import Path
from roundtable.official_knowledge import OfficialKnowledge

class OfficialTests(unittest.TestCase):
    def test_baseline_is_available_without_user_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            k=OfficialKnowledge(Path(tmp))
            info=k.public(); self.assertEqual(len(info['sources']),2)
            data=k.context('RegisterSystem 系统')
            self.assertIn('apidocs.html',str(data));self.assertIn('guide.html',str(data))
            self.assertTrue(data['evidence']);self.assertNotEqual(info['sources'][0]['status'],'ready')
            k.close()
