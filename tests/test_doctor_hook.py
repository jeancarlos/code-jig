import json
import unittest

from harness.doctor import check_hook
from harness.install import HOOK_STATUS
from tests.util import tree, write


class Hook(unittest.TestCase):
    def test_states(self):
        home = tree(self)
        self.assertEqual(check_hook(home)[0][0], "warn")
        write(home / "hooks.json", json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "c", "statusMessage": HOOK_STATUS}]}]}}))
        self.assertEqual(check_hook(home)[0][0], "ok")
        write(home / "hooks.json", "{bad")
        self.assertEqual(check_hook(home)[0][0], "FAIL")
