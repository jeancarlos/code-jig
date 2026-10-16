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

    def test_co_authored_by_claude_removed(self):
        path = self.root / "test.py"
        write(path, "# code\nCo-Authored-By: Claude Opus <noreply@anthropic.com>\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "# code\n")

    def test_co_authored_by_codex_removed(self):
        path = self.root / "test.py"
        write(path, "code\nCo-Authored-By: Codex <noreply@openai.com>\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\n")

    def test_generated_with_claude_code_removed(self):
        path = self.root / "test.py"
        write(path, "def f():\n    pass\nGenerated with [Claude Code]\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "def f():\n    pass\n")

    def test_generated_with_claude_removed(self):
        path = self.root / "test.py"
        write(path, "code\nGenerated with Claude\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\n")

    def test_robot_emoji_attribution_removed(self):
        path = self.root / "test.py"
        write(path, "code\n🤖 Generated with Claude\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\n")

    def test_ai_assisted_removed(self):
        path = self.root / "test.py"
        write(path, "code\nai-assisted code\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\n")

    def test_ai_generated_removed(self):
        path = self.root / "test.py"
        write(path, "code\nai-generated content\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\n")

    def test_multiple_attribution_lines_removed(self):
        path = self.root / "test.py"
        write(path, "code\nCo-Authored-By: Claude <x>\nGenerated with Claude Code\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\n")

    def test_attribution_case_insensitive(self):
        path = self.root / "test.py"
        write(path, "code\nCO-AUTHORED-BY: CLAUDE\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "code\n")


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
        content = "code\nCo-Authored-By: Claude\n"
        path.write_bytes(BOM + content.encode("utf-8"))
        strip_watermark(str(path), root=str(self.root))
        result = path.read_bytes()
        self.assertTrue(result.startswith(BOM))
        self.assertEqual(result, BOM + b"code\n")

    def test_bom_added_if_removed_watermark_lost_it(self):
        path = self.root / "test.txt"
        content = "code\nCo-Authored-By: Claude\n"
        path.write_bytes(BOM + content.encode("utf-8"))
        strip_watermark(str(path), root=str(self.root))
        result = path.read_bytes()
        self.assertTrue(result.startswith(BOM))


class WatermarkCRLF(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_crlf_preserved(self):
        path = self.root / "test.py"
        path.write_bytes(b"code\r\nCo-Authored-By: Claude\r\n")
        strip_watermark(str(path), root=str(self.root))
        result = path.read_bytes()
        self.assertEqual(result, b"code\r\n")

    def test_lf_preserved(self):
        path = self.root / "test.py"
        write(path, "code\nCo-Authored-By: Claude\n")
        strip_watermark(str(path), root=str(self.root))
        self.assertEqual(path.read_bytes(), b"code\n")


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
        self.assertEqual(path.read_text(encoding="utf-8"), "code\nremove\n")


if __name__ == "__main__":
    unittest.main()
