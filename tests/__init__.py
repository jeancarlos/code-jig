import atexit
import os
import shutil
import tempfile

_skills = tempfile.mkdtemp()
os.environ["CODEX_HARNESS_SKILLS_DIR"] = os.path.join(_skills, "agents skills")
atexit.register(shutil.rmtree, _skills, True)
