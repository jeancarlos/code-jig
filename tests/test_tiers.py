# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import tomllib
import unittest

from codejig import tiers
from codejig.install import render_profile
from codejig.tiers import Tier
from tests.util import tree, write

EFFORTS = 'default = "medium"\ndeep = "high"\nbulk = "low"\nreview = "high"\n'
MODELS = 'default = "m-a"\ndeep = "m-b"\nbulk = "m-c"\nreview = "n-d"\n'


class Load(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.core = root / "core-repo"
        self.ov = root / "overlay"
        write(self.core / "core" / "tiers.toml", EFFORTS)

    def test_order_and_values(self):
        write(self.ov / "profiles.toml", MODELS)
        self.assertEqual(tiers.load(self.core, self.ov), [
            Tier("default", "m-a", "medium"), Tier("deep", "m-b", "high"),
            Tier("bulk", "m-c", "low"), Tier("review", "n-d", "high")])

    def test_missing_file_names_it(self):
        with self.assertRaisesRegex(ValueError, "profiles.toml: not found"):
            tiers.load(self.core, self.ov)

    def test_malformed(self):
        write(self.ov / "profiles.toml", "default = \n")
        with self.assertRaisesRegex(ValueError, "profiles.toml"):
            tiers.load(self.core, self.ov)

    def test_missing_tier(self):
        write(self.ov / "profiles.toml", 'default = "m"\n')
        with self.assertRaisesRegex(ValueError, "no model for tier deep, bulk, review"):
            tiers.load(self.core, self.ov)

    def test_unknown_tier(self):
        write(self.ov / "profiles.toml", MODELS + 'fast = "x"\n')
        with self.assertRaisesRegex(ValueError, "unknown tier fast"):
            tiers.load(self.core, self.ov)

    def test_non_string(self):
        write(self.ov / "profiles.toml", MODELS.replace('"m-a"', "3"))
        with self.assertRaisesRegex(ValueError, "default must be a non-empty string"):
            tiers.load(self.core, self.ov)

    def test_bom_profiles(self):
        self.ov.mkdir(parents=True)
        (self.ov / "profiles.toml").write_bytes(b"\xef\xbb\xbf" + MODELS.encode())
        self.assertEqual(len(tiers.load(self.core, self.ov)), 4)


class Profile(unittest.TestCase):
    def test_body_without_policy(self):
        data = tomllib.loads(render_profile(Tier("deep", "m-b", "high"), ""))
        self.assertEqual(data, {"model": "m-b", "model_reasoning_effort": "high", "approvals_reviewer": "auto_review"})

    def test_policy_round_trips_exactly(self):
        ov = tree(self) / "overlay"
        raw = chr(0xFEFF) + '- "quoted" \\ back\tslash 🚀 del\x7f\r\n- second line\r\n'
        ov.mkdir(parents=True)
        (ov / "guardian-policy.md").write_bytes(raw.encode("utf-8"))
        policy = tiers.extra_policy(ov)
        data = tomllib.loads(render_profile(Tier("default", "m", "medium"), policy))
        self.assertEqual(data["auto_review"]["extra_policy"], raw.removeprefix(chr(0xFEFF)).replace("\r\n", "\n").strip())

    def test_compact_limit_is_a_top_level_key(self):
        data = tomllib.loads(render_profile(Tier("default", "m", "medium"), "- rule", 150000))
        self.assertEqual(data["model_auto_compact_token_limit"], 150000)
        self.assertNotIn("model_auto_compact_token_limit", data["auto_review"])

    def test_no_compact_limit_by_default(self):
        self.assertNotIn("model_auto_compact_token_limit", tomllib.loads(render_profile(Tier("default", "m", "medium"), "")))

    def test_memories_is_a_feature_flag(self):
        data = tomllib.loads(render_profile(Tier("default", "m", "medium"), "- rule", None, False))
        self.assertIs(data["features"]["memories"], False)
        self.assertEqual(data["auto_review"], {"extra_policy": "- rule"})

    def test_no_memories_flag_by_default(self):
        self.assertNotIn("features", tomllib.loads(render_profile(Tier("default", "m", "medium"), "")))

    def test_no_policy_file(self):
        ov = tree(self)
        self.assertEqual(tiers.extra_policy(ov), "")
