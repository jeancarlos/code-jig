import unittest

from codejig.watermark import BOM, strip_watermark
from tests.util import tree, write


class WatermarkInvisibleChars(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_zero_width_space_removed(self):
        path = self.root / "test.py"
        write(path, f"x{chr(0x200b)}y = 1\n")
        result = strip_watermark(str(path), root=str(self.root))
        self.assertIsInstance(result, dict)
        self.assertEqual(path.read_text(encoding="utf-8"), "xy = 1\n")

    def test_zero_width_non_joiner_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x200c)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_zero_width_joiner_removed(self):
        path = self.root / "test.py"
        write(path, f"x{chr(0x200d)}y\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "xy\n")

    def test_word_joiner_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2060)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_function_application_removed(self):
        path = self.root / "test.py"
        write(path, f"f{chr(0x2061)}x\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "fx\n")

    def test_invisible_times_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2062)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_invisible_separator_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2063)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_invisible_plus_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2064)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_mongolian_vowel_separator_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x180e)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_zero_width_no_break_space_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0xfeff)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_soft_hyphen_removed(self):
        path = self.root / "test.py"
        write(path, f"soft{chr(0x00ad)}hyphen\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "softhyphen\n")

    def test_narrow_no_break_space_becomes_regular_space(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x202f)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "a b\n")

    def test_no_break_space_becomes_regular_space(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x00a0)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "a b\n")

    def test_ltr_embedding_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x202a)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_rtl_embedding_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x202b)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_pop_directional_formatting_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x202c)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_ltr_override_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x202d)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_rtl_override_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x202e)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_ltr_isolate_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2066)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_rtl_isolate_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2067)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_first_strong_isolate_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2068)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")

    def test_pop_isolate_removed(self):
        path = self.root / "test.py"
        write(path, f"a{chr(0x2069)}b\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")


class WatermarkAttribution(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_attribution_lines_in_files_are_reported_not_deleted(self):
        for name, line in (("test.py", "Co-Authored-By: Claude Opus <noreply@anthropic.com>"),
                           ("test.py", "Co-Authored-By: Codex <noreply@openai.com>"),
                           ("notes.md", "Generated with [Claude Code](https://claude.com/claude-code)"),
                           ("notes.md", "Generated with Claude"),
                           ("notes.md", "\U0001f916 Generated with Claude"),
                           ("notes.txt", "AI-assisted: yes"),
                           ("config.yaml", "ai-generated: false"),
                           ("notes.md", "CO-AUTHORED-BY: CLAUDE")):
            with self.subTest(line=line):
                path = write(self.root / name, f"code\n{line}\n")
                result = strip_watermark(str(path), root=str(self.root))
                self.assertEqual(path.read_text(encoding="utf-8"), f"code\n{line}\n")
                self.assertFalse(result.get("changed"))
                self.assertEqual(result["attribution"], [2])


class WatermarkLegitimateContent(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_joiners_inside_emoji_and_words_survive(self):
        zwj, zwnj = chr(0x200D), chr(0x200C)
        family = chr(0x1F468) + zwj + chr(0x1F469) + zwj + chr(0x1F467)
        persian = chr(0x645) + chr(0x6CC) + zwnj + chr(0x62E) + chr(0x648) + chr(0x627) + chr(0x647) + chr(0x645)
        path = write(self.root / "notes.md", f"{family} {persian}\n")
        result = strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), f"{family} {persian}\n")
        self.assertFalse(result.get("changed"))

    def test_python_string_literals_keep_their_characters(self):
        zwj, zwsp = chr(0x200D), chr(0x200B)
        source = f'SEP = "{zwj}"\nNAME = f"x{zwsp}{{SEP}}"\nDOC = """\nGenerated by OpenAI\n"""\nx{zwsp}y = 1\n'
        path = write(self.root / "a.py", source)
        result = strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), source.replace(f"x{zwsp}y", "xy"))
        self.assertEqual((result["left"], result["attribution"]), ([1, 2], [4]))

    def test_code_and_data_files_are_reported_not_changed(self):
        zwsp = chr(0x200B)
        for name, text in (("app.js", f'const s = "a{zwsp}b";\n'), ("config.yaml", f"name: a{zwsp}b\n"),
                           ("broken.py", f's = """\nx{zwsp}\n')):
            with self.subTest(name=name):
                path = write(self.root / name, text)
                result = strip_watermark(str(path), root=str(self.root))
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                self.assertFalse(result.get("changed"))
                self.assertTrue(result["left"])

    def test_prose_loses_invisible_characters(self):
        path = write(self.root / "notes.md", f"a{chr(0x200B)}b\n")
        self.assertTrue(strip_watermark(str(path), root=str(self.root)).get("changed"))
        self.assertEqual(path.read_text(encoding="utf-8"), "ab\n")


class WatermarkBOM(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_bom_preserved_with_content(self):
        path = self.root / "test.txt"
        path.write_bytes(BOM + b"content\n")
        strip_watermark(str(path), root=str(self.root))
        result = path.read_bytes()
        self.assertTrue(result.startswith(BOM))
        self.assertEqual(result, BOM + b"content\n")

    def test_bom_preserved_with_watermark_removal(self):
        path = self.root / "test.txt"
        content = f"code\n{chr(0x200b)}x\n"
        path.write_bytes(BOM + content.encode("utf-8"))
        strip_watermark(str(path), root=str(self.root))
        result = path.read_bytes()
        self.assertTrue(result.startswith(BOM))
        self.assertEqual(result, BOM + b"code\nx\n")

    def test_bom_added_if_removed_watermark_lost_it(self):
        path = self.root / "test.txt"
        content = f"code\n{chr(0x200b)}x\n"
        path.write_bytes(BOM + content.encode("utf-8"))
        strip_watermark(str(path), root=str(self.root))
        result = path.read_bytes()
        self.assertTrue(result.startswith(BOM))


class WatermarkCRLF(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_crlf_preserved(self):
        path = self.root / "test.py"
        path.write_bytes(b"code\r\nx\xe2\x80\x8b\r\n")
        strip_watermark(str(path), root=str(self.root))
        result = path.read_bytes()
        self.assertEqual(result, b"code\r\nx\r\n")

    def test_lf_preserved(self):
        path = self.root / "test.py"
        write(path, f"code\nx{chr(0x200b)}\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_bytes(), b"code\nx\n")


class WatermarkNoOp(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_clean_file_not_rewritten(self):
        path = self.root / "test.py"
        content = b"def f():\n    pass\n"
        path.write_bytes(content)
        mtime_before = path.stat().st_mtime
        strip_watermark(str(path), root=str(self.root))
        mtime_after = path.stat().st_mtime
        self.assertEqual(mtime_before, mtime_after)
        self.assertEqual(path.read_bytes(), content)

    def test_visible_chars_preserved(self):
        path = self.root / "test.py"
        write(path, '# — em dash and "quotes" here\n')
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), '# — em dash and "quotes" here\n')


class WatermarkBinary(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_binary_file_skipped(self):
        path = self.root / "test.bin"
        content = bytes(range(256))
        path.write_bytes(content)
        result = strip_watermark(str(path), root=str(self.root))
        self.assertIsInstance(result, dict)
        self.assertEqual(path.read_bytes(), content)


class WatermarkNonExistent(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_nonexistent_file_returns_dict(self):
        path = self.root / "nonexistent.py"
        result = strip_watermark(str(path), root=str(self.root))
        self.assertIsInstance(result, dict)


class WatermarkSymlinks(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_symlink_inside_root_is_skipped(self):
        target = self.root / "real.py"
        write(target, f"code\n{chr(0x200b)}remove\n")
        symlink = self.root / "link.py"
        symlink.symlink_to(target)
        result = strip_watermark(str(symlink), root=str(self.root))
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("changed"))

    def test_symlink_outside_root_is_skipped(self):
        external = self.root.parent / "external.py"
        write(external, f"code\n{chr(0x200b)}remove\n")
        try:
            symlink = self.root / "link.py"
            symlink.symlink_to(external)
            result = strip_watermark(str(symlink), root=str(self.root))
            self.assertIsInstance(result, dict)
            self.assertFalse(result.get("changed"))
        finally:
            if external.exists():
                external.unlink()

    def test_regular_file_is_stripped(self):
        path = self.root / "test.py"
        write(path, f"code\n{chr(0x200b)}remove\nCo-Authored-By: Claude\n")
        result = strip_watermark(str(path), root=str(self.root))
        self.assertTrue(result.get("changed"))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\nremove\nCo-Authored-By: Claude\n")


if __name__ == "__main__":
    unittest.main()
