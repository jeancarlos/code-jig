import atexit
import os
import shutil
import tempfile
from unittest import mock

_skills = tempfile.mkdtemp()
os.environ["CODEX_HARNESS_SKILLS_DIR"] = os.path.join(_skills, "agents skills")
atexit.register(shutil.rmtree, _skills, True)

_claude_settings = mock.patch("harness.paths.claude_code_settings", return_value=None)
_claude_settings.start()
atexit.register(_claude_settings.stop)
