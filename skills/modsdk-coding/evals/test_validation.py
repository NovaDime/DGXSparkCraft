"""Behavior tests for the trusted validator; fixtures are temporary and never run."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("validate_modsdk", Path(__file__).parents[1] / "scripts" / "validate_modsdk.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ValidationBehavior(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def errors(self, runtime="python2"):
        return [row for row in validator.validate_project(self.root, runtime) if row["level"] == "error"]

    def test_python2_legacy_syntax_is_not_misclassified(self):
        self.write("rules.py", '# -*- coding: utf-8 -*-\nprint "中文"\n')
        self.assertFalse(self.errors())
        self.assertTrue(any(row["level"] == "warning" for row in validator.validate_project(self.root, "python2")))

    def test_python2_rejects_actual_python3_constructs(self):
        self.write("rules.py", "def name(value: str) -> str:\n    return f'{value}'\n")
        self.assertTrue(self.errors())
        self.assertFalse(self.errors("python3"))

    def test_comments_and_strings_do_not_trigger_syntax_rules(self):
        self.write("rules.py", '# async def fake(): return f"x"\ntext = "async def and await and f-string"\n')
        self.assertFalse(self.errors())

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', '{"a":']:
            with self.subTest(text=text):
                self.write("resource.json", text)
                self.assertTrue(self.errors())

    def test_known_wrong_side_is_rejected_but_entrypoint_is_allowed(self):
        self.write("server/feature.py", "from mod import client\n")
        self.assertTrue(self.errors())
        (self.root / "server/feature.py").unlink()
        self.write("modMain.py", "import mod.server.extraServerApi as serverApi\nimport mod.client.extraClientApi as clientApi\n")
        self.assertFalse(self.errors())

    def test_no_project_code_is_executed(self):
        marker = self.root / "executed.txt"
        self.write("danger.py", "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('ran')\n")
        validator.validate_project(self.root, "python3")
        self.assertFalse(marker.exists())

    def test_symlink_is_rejected(self):
        self.write("real.py", "value = 1\n")
        (self.root / "linked.py").symlink_to(self.root / "real.py")
        self.assertTrue(self.errors())

    def test_size_limit_is_reported_as_incomplete(self):
        self.write("large.py", "#" * (validator.MAX_FILE_BYTES + 1))
        self.assertTrue(self.errors())

    def test_python3_malformed_source_is_rejected(self):
        self.write("rules.py", "value =\n")
        self.assertTrue(self.errors("python3"))

    def test_nonascii_python2_requires_real_encoding_comment(self):
        self.write("rules.py", 'text = "coding:utf-8"\nlabel = "中文"\n')
        self.assertTrue(self.errors())
        self.write("rules.py", '# -*- coding: utf-8 -*-\nlabel = "中文"\n')
        self.assertFalse(self.errors())

    def test_deterministic_json_serializable_report(self):
        self.write("a.py", "value = 1\n")
        first = validator.validate_project(self.root, "python2")
        self.assertEqual(first, validator.validate_project(self.root, "python2"))
        self.assertEqual(first, json.loads(json.dumps(first)))


if __name__ == "__main__":
    unittest.main()
