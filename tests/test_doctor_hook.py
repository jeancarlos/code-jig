import json
import unittest

from codejig.doctor import check_hook
from codejig.install import HOOK_STATUS
from tests.util import tree, write


class Hook(unittest.TestCase):
    def test_states(self):
        home = tree(self)
        self.assertEqual(check_hook(home)[0][0], "warn")
        write(home / "hooks.json", json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "c", "statusMessage": HOOK_STATUS}]}]}}))
        self.assertEqual(check_hook(home)[0][0], "ok")
        write(home / "hooks.json", "{bad")
        self.assertEqual(check_hook(home)[0][0], "FAIL")

    def test_malformed_nested_hooks_reports_failure(self):
        home = tree(self)
        for hooks in (1, True, "command", {}, None, [1]):
            with self.subTest(hooks=hooks):
                write(home / "hooks.json", json.dumps({"hooks": {"Stop": [{"hooks": hooks}]}}))
                [(level, _, detail)] = check_hook(home)
                self.assertEqual(level, "FAIL")
                self.assertIn("hooks.json", detail)
