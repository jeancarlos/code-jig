import ast
import contextlib
import io
import unittest

from codejig.humanize import humanize_file
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
        humanize_file(str(path), root=str(self.root))
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


class HumanizeDocstrings(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def run_on(self, text):
        path = write(self.root / "d.py", text)
        result = humanize_file(str(path), root=str(self.root))
        return result, path.read_text(encoding="utf-8")

    def test_function_class_module_and_async_docstrings_are_cleaned(self):
        dash, ldq, rdq = chr(0x2014), chr(0x201C), chr(0x201D)
        text = (f'"""Module {dash} doc."""\n\n\nclass C:\n    """Class {dash} doc."""\n\n    def m(self):\n        """\n        Method {dash} doc {ldq}q{rdq}.\n        """\n\n\n'
                f'async def f():\n    """Async {dash} doc."""\n')
        result, out = self.run_on(text)
        self.assertEqual(result["dashes"], 4)
        self.assertEqual(out, text.replace(dash, "-").replace(ldq, '"').replace(rdq, '"'))
        ast.parse(out)

    def test_a_string_that_is_not_a_docstring_is_left_alone(self):
        dash = chr(0x2014)
        text = f'x = "a {dash} b"\n\n\ndef f():\n    y = "c {dash} d"\n    return y\n'
        result, out = self.run_on(text)
        self.assertFalse(result.get("changed"))
        self.assertEqual(out, text)

    def test_only_interior_boilerplate_lines_are_deleted_from_a_docstring(self):
        text = '"""Certainly! Summary."""\n\n\ndef f():\n    """\n    Summary.\n    I hope this helps\n    """\n'
        result, out = self.run_on(text)
        self.assertEqual(result["boilerplate"], 1)
        self.assertEqual(out, '"""Certainly! Summary."""\n\n\ndef f():\n    """\n    Summary.\n    """\n')

    def test_a_quote_rewrite_that_would_break_the_docstring_is_skipped(self):
        dash, ldq, rdq = chr(0x2014), chr(0x201C), chr(0x201D)
        text = f'def f():\n    """Say {dash} {ldq}hi{rdq}"""\n'
        result, out = self.run_on(text)
        ast.parse(out)
        self.assertIn(f"{ldq}hi{rdq}", out)
        self.assertIn("Say - ", out)


class HumanizeOtherLanguages(unittest.TestCase):
    D = chr(0x2014)

    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def run_on(self, name, text):
        path = write(self.root / name, text)
        result = humanize_file(str(path), root=str(self.root))
        return result, path.read_text(encoding="utf-8")

    def test_jsdoc_block_and_trailing_comments_are_cleaned(self):
        d = self.D
        text = f"/**\n * Adds {d} two numbers.\n * @param a first\n */\nfunction add(a, b) {{ return a + b; }} // sum {d} done\n"
        result, out = self.run_on("a.ts", text)
        self.assertEqual((result["dashes"], result.get("changed")), (2, True))
        self.assertEqual(out, text.replace(d, "-"))

    def test_line_doc_comments_in_rust_go_and_csharp(self):
        d = self.D
        for name, marker in (("a.rs", "///"), ("b.rs", "//!"), ("c.go", "//"), ("d.cs", "///"), ("e.java", "//")):
            with self.subTest(name=name):
                text = f"{marker} Does {d} work.\nint x;\n"
                result, out = self.run_on(name, text)
                self.assertEqual(out, text.replace(d, "-"))

    def test_a_marker_or_dash_inside_a_string_is_left_alone(self):
        d = self.D
        cases = {
            "a.js": f'const a = "x // {d} y"; const b = `\n// {d}\n`; const c = \'/* {d} */\';\n',
            "b.go": f'var s = `// {d}`\nvar t = "a // {d}"\n',
            "c.rs": f'let s = r#"// {d} "quoted""#;\nlet c = \'"\'; let t = "// {d}";\n',
            "d.cs": f'var v = @"// {d} ""q"" ";\nvar w = "// {d}";\n',
            "e.java": f'String t = """\n// {d}\n""";\nchar q = \'"\';\n',
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                result, out = self.run_on(name, text)
                self.assertEqual(out, text)
                self.assertFalse(result.get("changed"))

    def test_rust_lifetimes_do_not_swallow_the_rest_of_the_file(self):
        d = self.D
        text = f"fn f<'a>(x: &'a str) -> &'a str {{ x }} // keep {d} this\n"
        result, out = self.run_on("a.rs", text)
        self.assertEqual(out, text.replace(d, "-"))

    def test_css_only_has_block_comments(self):
        d = self.D
        result, out = self.run_on("a.css", f"a {{ background: url(//x.test/{d}.png); }} /* {d} */\n")
        self.assertEqual(out, f"a {{ background: url(//x.test/{d}.png); }} /* - */\n")

    def test_boilerplate_lines_inside_a_block_are_deleted_but_not_the_delimiters(self):
        text = "/* Here's the updated implementation:\n * Summary.\n * I hope this helps\n */\nint a;\n"
        result, out = self.run_on("a.c", text)
        self.assertEqual(result["boilerplate"], 1)
        self.assertEqual(out, "/* Here's the updated implementation:\n * Summary.\n */\nint a;\n")

    def test_a_comment_with_code_on_the_same_line_is_never_deleted(self):
        text = "/* Rest of the code */ int b = compute();\n"
        result, out = self.run_on("a.c", text)
        self.assertEqual(out, text)

    def test_line_comment_boilerplate_is_deleted(self):
        result, out = self.run_on("a.js", "// Let me know if delivery fails\nrun();\n")
        self.assertEqual((result["boilerplate"], out), (1, "run();\n"))

    def test_hash_languages_are_still_reported_not_edited(self):
        text = f"cat <<EOF\n# a {self.D} b\nEOF\n"
        result, out = self.run_on("d.sh", text)
        self.assertEqual(out, text)
        self.assertTrue(result.get("left"))


class HumanizeTells(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def run_on(self, name, text):
        path = write(self.root / name, text)
        result = humanize_file(str(path), root=str(self.root))
        return result, path.read_text(encoding="utf-8")

    def test_citation_leftovers_are_stripped_from_comments_and_docstrings(self):
        text = ('# Uses retries:contentReference[oaicite:3]{index=3} always [cite: 1, 2]\n'
                'def f():\n    """See https://example.com/a?utm_source=chatgpt.com for more oai_citation:1."""\n')
        result, out = self.run_on("a.py", text)
        self.assertEqual(result["citations"], 4)
        self.assertEqual(out, '# Uses retries always \ndef f():\n    """See https://example.com/a for more ."""\n')

    def test_a_citation_marker_in_code_or_a_string_is_left_alone(self):
        text = 'x = "[cite: 1]"\n'
        result, out = self.run_on("a.py", text)
        self.assertEqual(out, text)

    def test_bare_edit_narration_and_assistant_labels_are_deleted(self):
        text = "# removed\n# New\n# Updated:\n# AI: generated this helper\n# Updated to use a lock for thread safety\nx = 1\n"
        result, out = self.run_on("a.py", text)
        self.assertEqual(result["boilerplate"], 4)
        self.assertEqual(out, "# Updated to use a lock for thread safety\nx = 1\n")

    def test_more_chatbot_openers_are_deleted(self):
        text = "// Of course! here it is\n// You're absolutely right\n// Of course the cache is cold at boot\nrun();\n"
        result, out = self.run_on("a.js", text)
        self.assertEqual(result["boilerplate"], 2)
        self.assertEqual(out, "// Of course the cache is cold at boot\nrun();\n")

    def test_citations_are_reported_in_the_hook_message(self):
        from codejig.humanize import report_result
        msg = report_result({"file": "a.py", "changed": True, "citations": 2})
        self.assertIn("2 citations", msg)


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
        from codejig.__main__ import main
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
                self.assertIn(f"{path.name}: fixed 1 dashes", err.getvalue())


if __name__ == "__main__":
    unittest.main()
