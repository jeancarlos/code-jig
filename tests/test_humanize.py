import contextlib
import io
import unittest
from pathlib import Path

from harness.humanize import humanize_file
from tests.util import tree, write


class HumanizeDashes(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_em_dash_removed_in_comment(self):
        path = self.root / "test.py"
        write(path, "# This — is an em dash\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["dashes"], 1)
        self.assertIn("# This - is an em dash", path.read_text(encoding="utf-8"))

    def test_en_dash_removed_in_comment(self):
        path = self.root / "test.py"
        write(path, "# Range: 1 – 10\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["dashes"], 1)
        self.assertIn("# Range: 1 - 10", path.read_text(encoding="utf-8"))

    def test_code_lines_unchanged(self):
        path = self.root / "test.py"
        write(path, "code — value\nresult = 5\n")
        result = humanize_file(str(path), root=str(self.root))
        text = path.read_text(encoding="utf-8")
        self.assertFalse(result.get("changed"))


class HumanizeCurlyQuotes(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_curly_single_quotes_removed(self):
        path = self.root / "test.py"
        write(path, "# It’s ‘quoted’ here\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["quotes"], 3)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("‘", text)
        self.assertNotIn("’", text)

    def test_curly_double_quotes_removed(self):
        path = self.root / "test.py"
        write(path, "# He said “hello”\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["quotes"], 2)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("“", text)
        self.assertNotIn("”", text)


class HumanizeEllipsis(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_ellipsis_replaced(self):
        path = self.root / "test.py"
        write(path, "# Continue…\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["ellipsis"], 1)
        self.assertIn("# Continue...", path.read_text(encoding="utf-8"))


class HumanizeEmoji(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_emoji_removed_from_comment(self):
        path = self.root / "test.py"
        write(path, "# 🚀 Deploy\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["emoji"], 1)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("🚀", text)

    def test_emoji_not_removed_from_code(self):
        path = self.root / "test.py"
        write(path, "icon = '🚀'  # Launch\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        text = path.read_text(encoding="utf-8")
        self.assertIn("icon = '🚀'", text)
        self.assertIn("# Launch", text)


class HumanizeBoilerplate(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_add_more_as_needed_removed(self):
        path = self.root / "test.py"
        write(path, "# Add more as needed\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["boilerplate"], 1)

    def test_i_hope_this_helps_removed(self):
        path = self.root / "test.py"
        write(path, "# I hope this helps\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["boilerplate"], 1)

    def test_as_an_ai_removed(self):
        path = self.root / "test.py"
        write(path, "# As an AI\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["boilerplate"], 1)


class HumanizeLanguages(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_python_dash_in_comment(self):
        path = self.root / "test.py"
        write(path, "# Range — 1 to 10\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(result["dashes"], 1)


class HumanizeNoOp(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_clean_file_not_rewritten(self):
        path = self.root / "test.py"
        content = b"# Clean comment\ncode = 1\n"
        path.write_bytes(content)
        mtime_before = path.stat().st_mtime
        result = humanize_file(str(path), root=str(self.root))
        mtime_after = path.stat().st_mtime
        self.assertFalse(result.get("changed"))
        self.assertEqual(mtime_before, mtime_after)
        self.assertEqual(path.read_bytes(), content)

    def test_unsupported_extension_skipped(self):
        path = self.root / "test.unknown"
        write(path, "# Example usage:\ncode = 1\n")
        result = humanize_file(str(path), root=str(self.root))
        self.assertFalse(result.get("changed"))


class HumanizeSymlinks(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def test_symlink_skipped(self):
        target = self.root / "real.py"
        write(target, "# Example usage:\ncode = 1\n")
        symlink = self.root / "link.py"
        symlink.symlink_to(target)
        result = humanize_file(str(symlink), root=str(self.root))
        self.assertFalse(result.get("changed"))
        self.assertIn("Example usage", target.read_text(encoding="utf-8"))


class HumanizeCheck(unittest.TestCase):
    def test_check_does_not_write_files_or_directories(self):
        from harness.__main__ import main
        root = tree(self)
        path = root / "check.py"
        content = "# Range — 1 to 10\n"
        for target in (path, root):
            with self.subTest(target=target):
                write(path, content)
                before = path.stat().st_mtime_ns
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(main(["humanize", "--check", str(target)]), 1)
                self.assertEqual(path.read_text(encoding="utf-8"), content)
                self.assertEqual(path.stat().st_mtime_ns, before)
                self.assertIn(str(path), err.getvalue())


if __name__ == "__main__":
    unittest.main()
