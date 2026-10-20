# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import json
import unittest

from codejig.doctor import catalog, check_tiers, family
from codejig.install import run
from codejig.overlay import Overlay
from tests.util import tree, write

CATALOG = {"models": [
    {"slug": "m-a", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}]},
    {"slug": "n-b", "supported_reasoning_levels": [{"effort": "high"}]},
    {"slug": "bare"},
]}


class Tiers(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.core = root / "core-repo"
        write(self.core / "core" / "AGENTS.core.md", "core\n")
        write(self.core / "core" / "tiers.toml", 'default = "medium"\nreview = "high"\n')
        self.ov = Overlay(root / "overlay", "v0.2.0", True)
        write(self.ov.root / "profiles.toml", 'default = "m-a"\nreview = "n-b"\n')
        self.home = root / "codex home"
        run(self.core, self.ov, self.home)
        write(self.home / "models_cache.json", json.dumps(CATALOG))

    def levels(self):
        return {name: level for level, name, _ in check_tiers(self.home, self.core, self.ov)}

    def test_all_ok(self):
        self.assertEqual(set(self.levels().values()), {"ok"})

    def test_profile_with_compact_limit_is_current(self):
        ov = Overlay(self.ov.root, "v0.2.0", True, 150000)
        run(self.core, ov, self.home)
        levels = {name: level for level, name, _ in check_tiers(self.home, self.core, ov)}
        self.assertEqual(levels["tier default profile"], "ok")
        self.assertEqual(self.levels()["tier default profile"], "warn")

    def test_model_not_in_catalog_fails_with_candidates(self):
        write(self.ov.root / "profiles.toml", 'default = "zzz"\nreview = "n-b"\n')
        run(self.core, self.ov, self.home)
        detail = next(d for lv, n, d in check_tiers(self.home, self.core, self.ov) if n == "tier default model")
        self.assertIn("m-a", detail)
        self.assertEqual(self.levels()["tier default model"], "FAIL")

    def test_missing_model_names_its_family_first(self):
        write(self.ov.root / "profiles.toml", 'default = "m-zzz"\nreview = "n-b"\n')
        run(self.core, self.ov, self.home)
        detail = next(d for lv, n, d in check_tiers(self.home, self.core, self.ov) if n == "tier default model")
        self.assertIn("same family: m-a; candidates:", detail)

    def test_unsupported_effort_fails(self):
        write(self.ov.root / "profiles.toml", 'default = "n-b"\nreview = "m-a"\n')
        run(self.core, self.ov, self.home)
        self.assertEqual(self.levels()["tier review model"], "FAIL")

    def test_model_without_levels_skips_effort(self):
        write(self.ov.root / "profiles.toml", 'default = "bare"\nreview = "n-b"\n')
        run(self.core, self.ov, self.home)
        self.assertEqual(self.levels()["tier default model"], "ok")

    def test_missing_and_stale_profile_warn(self):
        (self.home / "default.config.toml").unlink()
        write(self.home / "review.config.toml", 'model = "x"\n')
        lv = self.levels()
        self.assertEqual((lv["tier default profile"], lv["tier review profile"]), ("warn", "warn"))

    def test_legacy_profile_in_config_fails(self):
        write(self.home / "config.toml", '[profiles.default]\nmodel = "x"\n')
        self.assertEqual(self.levels()["legacy profiles"], "FAIL")
        write(self.home / "config.toml", 'profile = "review"\n')
        self.assertEqual(self.levels()["legacy profiles"], "FAIL")

    def test_same_family_review_warns(self):
        write(self.ov.root / "profiles.toml", 'default = "m-a"\nreview = "m-a"\n')
        self.assertEqual(self.levels()["review family"], "warn")

    def test_bad_profiles_is_one_fail(self):
        write(self.ov.root / "profiles.toml", "x")
        [(level, name, _detail)] = check_tiers(self.home, self.core, self.ov)
        self.assertEqual((level, name), ("FAIL", "tiers"))


class Catalog(unittest.TestCase):
    def test_missing_invalid_wrong_shape(self):
        home = tree(self)
        self.assertIsNone(catalog(home))
        write(home / "models_cache.json", "{not json")
        self.assertIsNone(catalog(home))
        write(home / "models_cache.json", '{"models": {"a": 1}}')
        self.assertIsNone(catalog(home))
        write(home / "models_cache.json", '{"models": [1, {"slug": 2}, {"slug": "ok", "supported_reasoning_levels": [1]}]}')
        self.assertEqual(catalog(home), {"ok": set()})

    def test_odd_effort_values_are_ignored(self):
        home = tree(self)
        write(home / "models_cache.json", '{"models": [{"slug": "m", "supported_reasoning_levels": [{"effort": "low"}, {}, {"effort": ["x"]}, {"effort": 3}]}]}')
        self.assertEqual(catalog(home), {"m": {"low"}})

    def test_family(self):
        self.assertEqual(family("gpt-6-astra"), "gpt-6")
        self.assertEqual(family("gpt-5.6-sol"), "gpt-5.6")
        self.assertEqual(family("solo"), "solo")
