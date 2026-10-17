import os
import shutil
import sys
import unittest
from unittest import mock

from codejig import install
from codejig.install import SKILL_SIDECAR, install_skills, skill_sources, tree_digest
from tests.util import tree, write

SKILL = "---\nname: {n}\ndescription: test skill {n}\n---\n\nbody\n"


def skill(root, name, body=None):
    write(root / name / "SKILL.md", body or SKILL.format(n=name))
    return root / name


class Skills(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.core = self.root / "core-repo"
        self.ov = self.root / "overlay"
        self.dest = self.root / "agents" / "skills"
        skill(self.core / "skills", "grilling")

    def test_sources_and_clash(self):
        skill(self.ov / "skills", "mine")
        self.assertEqual(sorted(skill_sources(self.core, self.ov)), ["grilling", "mine"])
        skill(self.ov / "skills", "grilling")
        with self.assertRaisesRegex(ValueError, "grilling"):
            skill_sources(self.core, self.ov)

    def test_install_copies_with_sidecar(self):
        install_skills(skill_sources(self.core, self.ov), self.dest)
        got = self.dest / "grilling"
        self.assertEqual((got / "SKILL.md").read_text(encoding="utf-8"), SKILL.format(n="grilling"))
        self.assertEqual((got / SKILL_SIDECAR).read_text(encoding="utf-8").strip(), tree_digest(got))

    def test_user_skill_with_same_name_is_backed_up(self):
        skill(self.dest, "grilling", "---\nname: grilling\ndescription: mine\n---\nmine\n")
        lines = install_skills(skill_sources(self.core, self.ov), self.dest)
        self.assertEqual(list(self.dest.glob("grilling.bak-*")), [])
        [backup] = (self.dest.parent / "skills-backup").glob("grilling.bak-*")
        self.assertIn("mine", (backup / "SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue(any(str(backup) in line for line in lines))

    def test_reinstall_replaces_own_copy_without_backup(self):
        install_skills(skill_sources(self.core, self.ov), self.dest)
        write(self.core / "skills" / "grilling" / "SKILL.md", SKILL.format(n="grilling") + "v2\n")
        install_skills(skill_sources(self.core, self.ov), self.dest)
        self.assertEqual(list(self.dest.glob("grilling.bak-*")), [])
        self.assertIn("v2", (self.dest / "grilling" / "SKILL.md").read_text(encoding="utf-8"))

    def test_removed_skill_pruned_edited_copy_kept(self):
        skill(self.ov / "skills", "a")
        skill(self.ov / "skills", "b")
        install_skills(skill_sources(self.core, self.ov), self.dest)
        write(self.dest / "b" / "SKILL.md", "---\nname: b\ndescription: edited\n---\n")
        import shutil
        shutil.rmtree(self.ov / "skills" / "a")
        shutil.rmtree(self.ov / "skills" / "b")
        lines = install_skills(skill_sources(self.core, self.ov), self.dest)
        self.assertFalse((self.dest / "a").exists())
        self.assertTrue((self.dest / "b").exists())
        self.assertTrue(any(line.startswith("warning:") and "b" in line for line in lines))

    def test_unrelated_user_skills_untouched(self):
        mine = skill(self.dest, "other")
        install_skills(skill_sources(self.core, self.ov), self.dest)
        self.assertTrue((mine / "SKILL.md").exists())


    def test_evals_added_to_an_installed_copy_are_kept(self):
        install_skills(skill_sources(self.core, self.ov), self.dest)
        write(self.dest / "grilling" / "evals" / "case" / "a.txt", "mine\n")
        lines = install_skills(skill_sources(self.core, self.ov), self.dest)
        [backup] = (self.dest.parent / "skills-backup").glob("grilling.bak-*")
        self.assertEqual((backup / "evals" / "case" / "a.txt").read_text(encoding="utf-8"), "mine\n")
        self.assertTrue(any(str(backup) in line for line in lines))
        write(self.dest / "grilling" / "evals.toml", "[[case]]\n")
        shutil.rmtree(self.core / "skills" / "grilling")
        lines = install_skills(skill_sources(self.core, self.ov), self.dest)
        self.assertTrue((self.dest / "grilling" / "evals.toml").is_file())
        self.assertTrue(any(line.startswith("warning:") for line in lines))

    def test_a_failed_copy_keeps_the_installed_skill(self):
        install_skills(skill_sources(self.core, self.ov), self.dest)
        write(self.core / "skills" / "grilling" / "SKILL.md", SKILL.format(n="grilling") + "v2\n")
        with mock.patch.object(install.shutil, "copytree", side_effect=OSError("disk full")), self.assertRaises(OSError):
            install_skills(skill_sources(self.core, self.ov), self.dest)
        self.assertEqual((self.dest / "grilling" / "SKILL.md").read_text(encoding="utf-8"), SKILL.format(n="grilling"))
        self.assertEqual(sorted(p.name for p in self.dest.parent.iterdir()), ["skills"])
        install_skills(skill_sources(self.core, self.ov), self.dest)
        self.assertIn("v2", (self.dest / "grilling" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(sorted(p.name for p in self.dest.parent.iterdir()), ["skills"])

    def test_a_symlink_in_a_skill_source_is_refused(self):
        secret = write(self.root / "secret" / "id_rsa", "KEY\n")
        mine = skill(self.ov / "skills", "mine")
        try:
            (mine / "notes.md").symlink_to(secret)
        except OSError:
            self.skipTest("no symlinks here")
        with self.assertRaisesRegex(ValueError, "symlink"):
            skill_sources(self.core, self.ov)
        (mine / "notes.md").unlink()
        (mine / "refs").symlink_to(secret.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            skill_sources(self.core, self.ov)
        self.assertFalse(self.dest.exists())


RENAME = os.rename


def fake_exchange(a, b):
    middle = a.with_name(a.name + ".swap")
    RENAME(a, middle)
    RENAME(b, a)
    RENAME(middle, b)
    return True


class SkillSwap(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.core = self.root / "core-repo"
        self.dest = self.root / "agents" / "skills"
        self.src = skill(self.core / "skills", "grilling")
        self.installed = self.dest / "grilling" / "SKILL.md"
        self.missing = []
        self.exchanges = []

    def install(self):
        return install_skills(skill_sources(self.core, self.root / "overlay"), self.dest)

    def observe(self, *names):
        for module, name in names:
            real = getattr(module, name)

            def watched(*args, _real=real, **kwargs):
                if not self.installed.is_file():
                    self.missing.append(args)
                return _real(*args, **kwargs)

            patcher = mock.patch.object(module, name, watched)
            patcher.start()
            self.addCleanup(patcher.stop)

    def exchange(self, *results):
        answers = list(results)

        def run(a, b):
            self.exchanges.append((a, b))
            answer = answers.pop(0) if answers else True
            return fake_exchange(a, b) if answer is True else answer

        patcher = mock.patch.object(install, "_exchange", run)
        patcher.start()
        self.addCleanup(patcher.stop)

    def upgrade(self):
        self.install()
        write(self.src / "SKILL.md", SKILL.format(n="grilling") + "v2\n")

    def assert_clean(self):
        self.assertEqual(sorted(p.name for p in self.dest.parent.iterdir() if not p.name.startswith("skills-backup")), ["skills"])

    def test_with_an_exchange_the_installed_skill_never_goes_missing(self):
        self.upgrade()
        self.exchange(True)
        self.observe((os, "replace"), (os, "rename"), (install.shutil, "move"), (install.shutil, "rmtree"))
        self.install()
        self.assertEqual(len(self.exchanges), 1)
        self.assertEqual(self.missing, [])
        self.assertIn("v2", self.installed.read_text(encoding="utf-8"))
        self.assert_clean()
        self.assertFalse((self.dest.parent / "skills-backup").exists())

    def test_a_user_skill_is_swapped_out_and_backed_up_without_a_gap(self):
        skill(self.dest, "grilling", "---\nname: grilling\ndescription: mine\n---\nmine\n")
        self.exchange(True)
        self.observe((os, "replace"), (install.shutil, "move"), (install.shutil, "rmtree"))
        lines = self.install()
        self.assertEqual(self.missing, [])
        [backup] = (self.dest.parent / "skills-backup").glob("grilling.bak-*")
        self.assertIn("mine", (backup / "SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue(any(str(backup) in line for line in lines))
        self.assertEqual(self.installed.read_text(encoding="utf-8"), SKILL.format(n="grilling"))
        self.assert_clean()

    def test_without_an_exchange_two_renames_are_used(self):
        self.upgrade()
        self.exchange(False)
        self.observe((os, "replace"))
        self.install()
        self.assertEqual(len(self.exchanges), 1)
        self.assertEqual(len(self.missing), 1)
        self.assertIn("v2", self.installed.read_text(encoding="utf-8"))
        self.assert_clean()

    def test_without_an_exchange_a_failed_second_rename_puts_the_old_skill_back(self):
        self.upgrade()
        self.exchange(False)
        real = os.replace

        def replace(src, dst):
            if os.path.basename(src) == "grilling" and os.path.basename(os.path.dirname(src)).startswith(".code-jig-"):
                raise OSError("busy")
            return real(src, dst)

        with mock.patch.object(os, "replace", replace), self.assertRaisesRegex(OSError, "busy"):
            self.install()
        self.assertEqual(self.installed.read_text(encoding="utf-8"), SKILL.format(n="grilling"))
        self.assert_clean()

    def test_a_failed_backup_after_the_exchange_swaps_the_user_skill_back(self):
        mine = "---\nname: grilling\ndescription: mine\n---\nmine\n"
        skill(self.dest, "grilling", mine)
        self.exchange(True, True)
        with mock.patch.object(install.shutil, "move", side_effect=OSError("backup disk full")), \
                self.assertRaisesRegex(OSError, "backup disk full"):
            self.install()
        self.assertEqual(len(self.exchanges), 2)
        self.assertEqual(self.installed.read_text(encoding="utf-8"), mine)
        self.assert_clean()

    def test_when_even_the_swap_back_fails_the_user_skill_is_kept_and_named(self):
        mine = "---\nname: grilling\ndescription: mine\n---\nmine\n"
        skill(self.dest, "grilling", mine)
        self.exchange(True, False)
        with mock.patch.object(install.shutil, "move", side_effect=OSError("backup disk full")), \
                self.assertRaises(ValueError) as caught:
            self.install()
        kept = [p for p in self.dest.parent.glob(".code-jig-grilling-*/grilling") if (p / "SKILL.md").is_file()]
        self.assertEqual(len(kept), 1)
        self.assertEqual((kept[0] / "SKILL.md").read_text(encoding="utf-8"), mine)
        self.assertIn(str(kept[0]), str(caught.exception))
        self.assertEqual(self.installed.read_text(encoding="utf-8"), SKILL.format(n="grilling"))

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "renameat2 and renamex_np exist only on Linux and macOS")
    def test_the_os_exchange_swaps_two_folders_in_one_step(self):
        a, b = write(self.root / "a" / "f", "a\n").parent, write(self.root / "b" / "f", "b\n").parent
        if not install._exchange(a, b):
            self.skipTest("this filesystem has no exchange")
        self.assertEqual(((a / "f").read_text(encoding="utf-8"), (b / "f").read_text(encoding="utf-8")), ("b\n", "a\n"))

    def test_an_exchange_that_the_os_refuses_reports_false_and_changes_nothing(self):
        a, b = write(self.root / "a" / "f", "a\n").parent, self.root / "missing"
        self.assertFalse(install._exchange(a, b))
        self.assertEqual((a / "f").read_text(encoding="utf-8"), "a\n")
        self.assertFalse(b.exists())


class RealHomeIsolation(unittest.TestCase):
    def test_tests_never_target_the_real_skills_folder(self):
        from pathlib import Path

        from codejig import paths
        self.assertNotEqual(paths.agents_skills(), Path.home() / ".agents" / "skills")

    def test_tests_never_target_the_real_claude_settings(self):
        from pathlib import Path

        from codejig import paths
        self.assertNotEqual(paths.claude_code_settings(), Path.home() / ".claude" / "settings.json")
