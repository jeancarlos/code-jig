import tomllib
import unittest
from pathlib import Path
from unittest import mock

from codejig import managed, paths
from codejig.managed import check_requirements
from codejig.tiers import Tier
from tests.util import tree, write

TS = [Tier("default", "m-a", "medium"), Tier("review", "n-b", "high")]
BENCH = 'allowed_approvals_reviewers = ["user", "auto_review"]\ncheck_for_update_on_startup = false\n'


class Requirements(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.bench = write(self.root / "bench.toml", BENCH)
        self.req = self.root / "requirements.toml"

    def levels(self):
        return {n: lv for lv, n, _ in check_requirements(self.req, self.bench, TS)}

    def detail(self, name):
        return [d for lv, n, d in check_requirements(self.req, self.bench, TS) if n == name][0]

    def test_absent_says_cloud_is_invisible(self):
        [(level, _, detail), *_] = check_requirements(self.req, self.bench, TS)
        self.assertEqual(level, "ok")
        self.assertIn("cloud", detail)

    def test_same_as_bench_ok(self):
        write(self.req, BENCH)
        self.assertEqual(set(self.levels().values()), {"ok"})

    def test_auto_review_not_allowed_fails(self):
        write(self.req, 'allowed_approvals_reviewers = ["user"]\n')
        self.assertEqual(self.levels()["guardian allowed"], "FAIL")

    def test_ignore_rules_hits_tier_model(self):
        write(self.req, '[auto_review]\nignore_rules = ["n-b", "other"]\n')
        detail = self.detail("overlay rules")
        self.assertIn("n-b", detail)
        self.assertNotIn("other", detail)

    def test_managed_hooks_and_policy_warn(self):
        write(self.req, 'allow_managed_hooks_only = true\nguardian_extra_policy = "x"\n')
        lv = self.levels()
        self.assertEqual((lv["hooks"], lv["guardian policy"]), ("warn", "warn"))

    def test_bench_diff_names_keys(self):
        write(self.req, 'allowed_sandbox_modes = ["read-only"]\ncheck_for_update_on_startup = true\n')
        detail = self.detail("bench diff")
        self.assertIn("allowed_sandbox_modes", detail)
        self.assertIn("allowed_approvals_reviewers", detail)
        self.assertIn("check_for_update_on_startup", detail)

    def test_malformed_fails(self):
        write(self.req, "x = \n")
        self.assertEqual(check_requirements(self.req, self.bench, TS)[0][0], "FAIL")

    def test_wrong_types_do_not_crash(self):
        write(self.req, 'auto_review = "x"\nallowed_approvals_reviewers = "auto_review"\n')
        self.assertNotIn("FAIL", self.levels().values())

    def test_paths(self):
        with mock.patch.object(managed.sys, "platform", "linux"):
            self.assertEqual(managed.requirements_path(), Path("/etc/codex/requirements.toml"))
        with mock.patch.object(managed.sys, "platform", "win32"), mock.patch.dict(managed.os.environ, {"ProgramData": "D:\\PD"}):
            self.assertEqual(managed.requirements_path(), Path("D:\\PD") / "OpenAI" / "Codex" / "requirements.toml")

    def test_shipped_bench_file_allows_auto_review(self):
        data = tomllib.loads((paths.CORE / "bench" / "requirements.toml").read_text(encoding="utf-8"))
        self.assertIn("auto_review", data["allowed_approvals_reviewers"])
