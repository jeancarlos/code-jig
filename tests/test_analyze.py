# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from codejig import analyze, unsafe_scan
from tests.util import tree, write

LIZARD_CSV = textwrap.dedent('''\
    9,8,51,1,9,"f@2-10@./src/a.py","./src/a.py","f","f( x )",2,10,17
    120,16,900,8,130,"g@20-150@./src/a.py","./src/a.py","g","g( a, b )",20,150,3
    3,1,10,0,3,"h@1-3@./src/b.py","./src/b.py","h","h( )",1,3,0
    Duplicates
    ===================================
    Duplicate block:
    --------------------------
    ./src/c.py:1 ~ 23
    ./src/d.py:4 ~ 26
    ^^^^^^^^^^^^^^^^^^^^^^^^^^

    Total duplicate rate: 7.00%
''')


def launcher(bindir: Path, name: str, argv: list[str]) -> None:
    if os.name == "nt":
        (bindir / f"{name}.cmd").write_text("@" + " ".join(f'"{a}"' for a in argv) + " %*\r\n", encoding="utf-8")
    else:
        path = bindir / name
        path.write_text("#!/bin/sh\nexec " + " ".join(f'"{a}"' for a in argv) + ' "$@"\n', encoding="utf-8")
        path.chmod(0o755)


def fake_tool(bindir: Path, name: str, stdout: str = "", code: int = 0, sleep: float = 0, body: str | None = None) -> None:
    script = bindir / f"{name}_impl.py"
    script.write_text(body or textwrap.dedent(f'''\
        import sys, time
        time.sleep({sleep!r})
        sys.stdout.write({stdout!r})
        sys.stderr.write("stderr of {name}\\n")
        sys.exit({code})
    '''), encoding="utf-8")
    launcher(bindir, name, [sys.executable, str(script)])


def git(cwd, *args):
    subprocess.run([shutil.which("git") or "git", "-c", "user.email=a@b", "-c", "user.name=a", *args], cwd=cwd, check=True, capture_output=True)


class Detect(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_none(self):
        self.assertEqual(analyze.detect(self.root), set())

    def test_each_stack(self):
        write(self.root / "pyproject.toml", "")
        write(self.root / "package.json", "{}")
        write(self.root / "svc" / "Svc.csproj", "<Project/>")
        self.assertEqual(analyze.detect(self.root), {"python", "node", "dotnet"})

    def test_python_by_loose_file(self):
        write(self.root / "tool.py", "")
        self.assertEqual(analyze.detect(self.root), {"python"})

    def test_python_package_without_packaging_files(self):
        write(self.root / "pkg" / "__init__.py", "")
        self.assertEqual(analyze.detect(self.root), {"python"})

    def test_rust_java_go_by_marker(self):
        write(self.root / "Cargo.toml", "")
        write(self.root / "build.gradle.kts", "")
        write(self.root / "go.mod", "")
        self.assertEqual(analyze.detect(self.root), {"rust", "java", "go"})

    def test_rust_only_tree_is_not_python(self):
        write(self.root / "Cargo.toml", "")
        write(self.root / "src" / "main.rs", "fn main() {}\n")
        write(self.root / "target" / "gen.py", "x = 1\n")
        write(self.root / ".venv" / "a.py", "x = 1\n")
        self.assertEqual(analyze.detect(self.root), {"rust"})

    def test_python_script_beside_rust_is_still_python(self):
        write(self.root / "Cargo.toml", "")
        write(self.root / "tools" / "icons.py", "x = 1\n")
        self.assertEqual(analyze.detect(self.root), {"rust", "python"})

    def test_java_by_pom(self):
        write(self.root / "pom.xml", "")
        self.assertEqual(analyze.detect(self.root), {"java"})

    def test_nested_projects_are_found_one_folder_down(self):
        write(self.root / "src-tauri" / "Cargo.toml", "")
        write(self.root / "backend" / "go.mod", "")
        write(self.root / "target" / "debug" / "pom.xml", "")
        self.assertEqual(analyze.detect(self.root), {"rust", "go"})

    def test_rust_and_go_tools_run_in_the_nested_project(self):
        write(self.root / "src-tauri" / "Cargo.toml", "")
        write(self.root / "backend" / "go.mod", "")
        by = {t.name: t for t in analyze.TOOLS}
        clippy = by["clippy"].argv("cargo", self.root, self.root)
        self.assertEqual(clippy[clippy.index("--manifest-path") + 1], str(self.root / "src-tauri" / "Cargo.toml"))
        vet = by["go-vet"].argv("go", self.root, self.root)
        self.assertEqual(vet[:3], ["go", "-C", str(self.root / "backend")])

    def test_dotnet_by_solution(self):
        write(self.root / "App.slnx", "")
        self.assertEqual(analyze.detect(self.root), {"dotnet"})


class Resolve(unittest.TestCase):
    def test_repo_node_bin_wins(self):
        root = tree(self)
        bindir = root / "node_modules" / ".bin"
        bindir.mkdir(parents=True)
        fake_tool(bindir, "eslint")
        found = analyze.resolve("eslint", root, "node")
        self.assertIsNotNone(found)
        self.assertTrue(Path(found).parent == bindir)

    def test_missing(self):
        self.assertIsNone(analyze.resolve("no-such-tool-xyz", tree(self), "any"))


class Parsers(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.tmp = tree(self)

    def test_lizard(self):
        found = analyze.parse_lizard(LIZARD_CSV, self.root, self.tmp)
        by_rule = {(f.rule, f.path, f.line) for f in found}
        self.assertIn(("cognitive-complexity", "src/a.py", 2), by_rule)
        self.assertIn(("cyclomatic-complexity", "src/a.py", 20), by_rule)
        self.assertIn(("function-length", "src/a.py", 20), by_rule)
        self.assertIn(("parameters", "src/a.py", 20), by_rule)
        self.assertIn(("duplicate-block", "src/c.py", 1), by_rule)
        self.assertNotIn("src/b.py", {f.path for f in found})
        dup = next(f for f in found if f.category == "duplication")
        self.assertIn("src/d.py:4", dup.message)
        cog = next(f for f in found if f.rule == "cognitive-complexity")
        self.assertIn("17", cog.message)

    def test_lizard_lists_only_source_code(self):
        for name in ("a.py", "b.cs", "c.ts", "d.tsx", "e.js", "data.json", "f.jsonl", "README.md", "node_modules/x/y.js"):
            write(self.root / name, "x\n")
        args = analyze._lizard_args("lizard", self.root, self.tmp)
        listed = (self.tmp / "files.txt").read_text(encoding="utf-8").split()
        self.assertEqual(listed, ["a.py", "b.cs", "c.ts", "d.tsx", "e.js"])
        self.assertEqual(args[-2:], ["-f", str(self.tmp / "files.txt")])

    def test_source_files_skip_generated_dirs_in_a_git_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for name in ("a.py", "coverage/lcov-report/p.js", "pkg/htmlcov/q.py", "pkg/coverage.py"):
            write(self.root / name, "x\n")
        self.assertEqual(analyze.source_files(self.root), ["a.py", "pkg/coverage.py"])

    def test_lizard_empty_and_garbage(self):
        self.assertEqual(analyze.parse_lizard("", self.root, self.tmp), [])
        self.assertEqual(analyze.parse_lizard("not,a,lizard,row\n", self.root, self.tmp), [])

    def test_ruff(self):
        out = json.dumps([
            {"code": "S602", "message": "shell=True", "filename": str(self.root / "a.py"), "location": {"row": 9}},
            {"code": "B006", "message": "mutable default", "filename": str(self.root / "b.py"), "location": {"row": 2}},
            {"code": None, "message": "SyntaxError", "filename": str(self.root / "c.py"), "location": {"row": 1}},
        ])
        found = analyze.parse_ruff(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.path, f.line) for f in found],
                         [("security", "a.py", 9), ("bug", "b.py", 2), ("bug", "c.py", 1)])
        self.assertEqual(found[2].rule, "syntax")

    def test_ruff_only_flake8_bandit_codes_are_security(self):
        out = json.dumps([{"code": c, "message": "m", "filename": "a.py", "location": {"row": 1}} for c in ("S608", "SIM102", "SLF001")])
        self.assertEqual([f.category for f in analyze.parse_ruff(out, self.root, self.tmp)], ["security", "bug", "bug"])

    def test_ruff_rejects_non_list(self):
        with self.assertRaises(ValueError):
            analyze.parse_ruff('{"x": 1}', self.root, self.tmp)

    def test_mypy(self):
        out = "src/a.py:3: error: Incompatible types  [assignment]\nsrc/a.py:4: note: see here\nSuccess: no issues\n"
        [f] = analyze.parse_mypy(out, self.root, self.tmp)
        self.assertEqual((f.category, f.rule, f.path, f.line), ("type", "assignment", "src/a.py", 3))

    def test_mypy_with_column_numbers(self):
        [f] = analyze.parse_mypy("src/a.py:3:5: error: Bad  [misc]\n", self.root, self.tmp)
        self.assertEqual((f.path, f.line), ("src/a.py", 3))
        found = analyze.parse_mypy("src/b.py:4:1:4:9: error: Worse  [misc]\n", self.root, self.tmp)
        self.assertEqual([(f.path, f.line, f.rule) for f in found], [("src/b.py", 4, "misc")])

    def test_eslint(self):
        out = json.dumps([{"filePath": str(self.root / "src" / "x.ts"), "messages": [
            {"ruleId": "sonarjs/cognitive-complexity", "line": 5, "message": "too complex"},
            {"ruleId": "security/detect-eval-with-expression", "line": 7, "message": "eval"},
            {"ruleId": "no-unused-vars", "line": 9, "message": "unused"},
            {"ruleId": None, "line": 1, "message": "Parsing error"},
            {"ruleId": "sonarjs/no-hardcoded-passwords", "line": 3, "message": "password"},
        ]}])
        found = analyze.parse_eslint(out, self.root, self.tmp)
        self.assertEqual([f.category for f in found], ["complexity", "security", "bug", "bug", "security"])
        self.assertEqual(found[3].rule, "parse")
        self.assertEqual(found[0].path, "src/x.ts")

    def test_tsc(self):
        out = "src/x.ts(4,7): error TS2322: Type 'string' is not assignable.\nsomething else\n"
        [f] = analyze.parse_tsc(out, self.root, self.tmp)
        self.assertEqual((f.category, f.rule, f.path, f.line), ("type", "TS2322", "src/x.ts", 4))

    def test_dotnet_dedupes_and_categorises(self):
        line = f"{self.root / 'Svc' / 'A.cs'}(10,5): warning S3776: Refactor this method [{self.root / 'Svc' / 'Svc.csproj'}]"
        out = (f"{line}\n{line}\nSvc/B.cs(3,1): warning CA5350: Weak crypto\n"
               "Svc/C.cs(8,2): error CS0103: The name 'x' does not exist\n"
               "Svc/D.cs(1,1): warning RCS1163: Unused parameter\nBuild FAILED.")
        found = analyze.parse_dotnet(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.path) for f in found], [
            ("complexity", "S3776", "Svc/A.cs"), ("security", "CA5350", "Svc/B.cs"),
            ("type", "CS0103", "Svc/C.cs"), ("bug", "RCS1163", "Svc/D.cs")])
        self.assertEqual(found[0].message, "Refactor this method")

    def test_dotnet_project_level_warnings(self):
        proj = str(self.root / "Api" / "Api.csproj")
        out = "\n".join([
            f"{proj} : warning NU1903: Package 'Newtonsoft.Json' 12.0.1 has a known high severity vulnerability, https://github.com/advisories/GHSA-5crp-9r3c-p9vr [{proj}]",
            f"{proj} : warning NU1903: O pacote 'Newtonsoft.Json' 12.0.1 tem uma alta vulnerabilidade de gravidade conhecida, https://github.com/advisories/GHSA-5crp-9r3c-p9vr",
            f"{proj} : warning NU1900: Error occurred while getting package vulnerability data",
            f"{proj} : error NETSDK1045: The current .NET SDK does not support targeting .NET 99.0",
        ])
        found = analyze.parse_dotnet(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.path, f.line) for f in found], [
            ("dependency", "NU1903", "Api/Api.csproj", 0), ("dependency", "NU1903", "Api/Api.csproj", 0),
            ("bug", "NU1900", "Api/Api.csproj", 0), ("bug", "NETSDK1045", "Api/Api.csproj", 0)])
        self.assertIn("GHSA-5crp-9r3c-p9vr", found[0].message)
        self.assertNotIn("[", found[0].message.split("https")[0])

    def test_clippy(self):
        def msg(level, code, name, primary=True):
            return json.dumps({"reason": "compiler-message", "message": {
                "level": level, "message": f"{name} problem", "code": {"code": code} if code else None,
                "spans": [{"file_name": "src/lib.rs", "line_start": 7, "is_primary": primary}]}})
        out = "\n".join([
            msg("warning", "clippy::cognitive_complexity", "big"), msg("warning", "unused_variables", "unused"),
            msg("warning", "clippy::needless_return", "ret"), msg("error", "E0308", "types"), msg("warning", None, "plain"),
            msg("warning", "clippy::skipped", "secondary", primary=False),
            json.dumps({"reason": "compiler-artifact"}), json.dumps({"reason": "compiler-message", "message": {"level": "note", "spans": []}}),
            ""])
        found = analyze.parse_clippy(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.path, f.line) for f in found], [
            ("complexity", "clippy::cognitive_complexity", "src/lib.rs", 7), ("unused", "unused_variables", "src/lib.rs", 7),
            ("bug", "clippy::needless_return", "src/lib.rs", 7), ("type", "E0308", "src/lib.rs", 7), ("bug", "warning", "src/lib.rs", 7)])

    def test_go_vet(self):
        one = {"example.com/m": {"printf": [{"posn": str(self.root / "main.go") + ":5:2", "message": "wrong type"}]}}
        two = {"example.com/n": {"unusedresult": [{"posn": "b.go:9:1", "message": "result unused"}], "empty": None}}
        out = json.dumps(one, indent="\t") + "\n" + json.dumps(two, indent="\t") + "\n"
        found = analyze.parse_go_vet(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.path, f.line) for f in found], [
            ("bug", "printf", "main.go", 5), ("bug", "unusedresult", "b.go", 9)])
        self.assertEqual(analyze.parse_go_vet("", self.root, self.tmp), [])

    def test_pmd(self):
        def v(rule, ruleset, line):
            return {"rule": rule, "ruleset": ruleset, "beginline": line, "description": f"{rule} here"}
        out = json.dumps({"files": [{"filename": str(self.root / "src" / "A.java"), "violations": [
            v("CyclomaticComplexity", "Design", 3), v("UnusedLocalVariable", "Best Practices", 4),
            v("HardCodedCryptoKey", "Security", 5), v("EmptyCatchBlock", "Error Prone", 6)]}, {"filename": "B.java"}]})
        found = analyze.parse_pmd(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.path, f.line) for f in found], [
            ("complexity", "CyclomaticComplexity", "src/A.java", 3), ("unused", "UnusedLocalVariable", "src/A.java", 4),
            ("security", "HardCodedCryptoKey", "src/A.java", 5), ("bug", "EmptyCatchBlock", "src/A.java", 6)])

    def test_pmd_rejects_non_object(self):
        with self.assertRaises(ValueError):
            analyze.parse_pmd("[]", self.root, self.tmp)

    def test_vulture(self):
        out = textwrap.dedent("""\
            m.py:1: unused import 'os' (90% confidence)
            pkg/m.py:6: unused function 'unused_func' (60% confidence)
            pkg/m.py:12: unreachable code after 'return' (100% confidence, 2 lines)
            pkg/m.py:20: unsatisfiable 'if' condition (100% confidence, 2 lines)
            pkg/m.py:24: unreachable 'else' block (100% confidence, 3 lines)
            C:\\work dir\\pkg\\w.py:7: unused variable 'x' (100% confidence)
            not a vulture line
        """)
        found = analyze.parse_vulture(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.path, f.line) for f in found[:5]], [
            ("unused", "unused-import", "m.py", 1), ("unused", "unused-function", "pkg/m.py", 6),
            ("unused", "unreachable-code-after", "pkg/m.py", 12), ("unused", "unsatisfiable-condition", "pkg/m.py", 20),
            ("unused", "unreachable-block", "pkg/m.py", 24)])
        self.assertEqual(len(found), 6)
        self.assertEqual((found[5].rule, found[5].line), ("unused-variable", 7))
        self.assertTrue(found[5].path.replace("\\", "/").endswith("work dir/pkg/w.py"))
        self.assertEqual(found[0].message, "unused import 'os' (90% confidence)")

    def test_knip(self):
        out = json.dumps({"issues": [
            {"file": "package.json", "dependencies": [{"name": "lodash"}, {"name": "is-odd"}], "devDependencies": [], "unlisted": []},
            {"file": "src/e.ts", "enumMembers": [{"name": "B", "namespace": "E", "line": 4}]},
            {"file": "src/util.ts", "exports": [{"name": "helper", "line": 3, "col": 14}], "types": [{"name": "Shape", "line": 9}]},
            {"file": "src/old.ts", "files": [{"name": "src/old.ts"}]},
            {"file": "src/app.ts", "unlisted": [{"name": "chalk"}], "unresolved": [{"name": "./gone", "line": 2}]},
            {"file": "src/a.ts", "cycles": [[{"name": "src/a.ts"}, {"name": "src/b.ts"}]]},
        ]})
        found = analyze.parse_knip(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.path, f.line) for f in found], [
            ("unused", "knip/dependencies", "package.json", 0), ("unused", "knip/dependencies", "package.json", 0),
            ("unused", "knip/enumMembers", "src/e.ts", 4), ("unused", "knip/exports", "src/util.ts", 3),
            ("unused", "knip/types", "src/util.ts", 9), ("unused", "knip/files", "src/old.ts", 0),
            ("bug", "knip/unlisted", "src/app.ts", 0), ("bug", "knip/unresolved", "src/app.ts", 2),
            ("bug", "knip/cycles", "src/a.ts", 0)])
        self.assertIn("is-odd", found[1].message)
        self.assertIn("E.B", found[2].message)
        self.assertIn("helper", found[3].message)
        self.assertIn("src/b.ts", found[-1].message)

    def test_vulture_args(self):
        [tool] = [t for t in analyze.TOOLS if t.name == "vulture"]
        args = tool.argv("vulture", self.root, self.tmp)
        excludes = args[args.index("--exclude") + 1].split(",")
        self.assertIn("bin/*", excludes)
        self.assertIn("*/bin/*", excludes)
        self.assertNotIn("bin", excludes)
        write(self.root / "pyproject.toml", "[tool.vulture]\npaths = ['src', 'whitelist.py']\n")
        self.assertEqual(tool.argv("vulture", self.root, self.tmp), ["vulture"])

    def test_knip_rejects_wrong_shape(self):
        with self.assertRaises(ValueError):
            analyze.parse_knip("[]", self.root, self.tmp)

    def test_semgrep(self):
        out = json.dumps({"results": [{"check_id": "r.sql", "path": "a.py", "start": {"line": 3}, "extra": {"message": "sqli"}}], "errors": []})
        [f] = analyze.parse_semgrep(out, self.root, self.tmp)
        self.assertEqual((f.category, f.rule, f.line), ("security", "r.sql", 3))

    def test_semgrep_errors_are_reported_with_the_findings(self):
        out = json.dumps({"results": [{"check_id": "r.sql", "path": "a.py", "start": {"line": 3}, "extra": {"message": "sqli"}}],
                          "errors": [{"type": "Timeout", "level": "warn", "message": "b.py timed out"}, {"type": "Syntax error"}]})
        with self.assertRaises(analyze.Partial) as ctx:
            analyze.parse_semgrep(out, self.root, self.tmp)
        self.assertEqual([f.rule for f in ctx.exception.findings], ["r.sql"])
        self.assertIn("2 errors", str(ctx.exception))
        self.assertIn("b.py timed out", str(ctx.exception))

    def test_gitleaks_never_prints_secret(self):
        write(self.tmp / "gitleaks.json", json.dumps([{"RuleID": "aws", "File": "cfg.env", "StartLine": 2,
                                                      "Description": "AWS key", "Secret": "AKIAEXAMPLE", "Match": "AKIAEXAMPLE"}]))
        [f] = analyze.parse_gitleaks("", self.root, self.tmp)
        self.assertEqual((f.category, f.path, f.line), ("secret", "cfg.env", 2))
        self.assertNotIn("AKIA", f.message)

    def test_gitleaks_message_carries_fingerprint(self):
        write(self.tmp / "gitleaks.json", json.dumps([{"RuleID": "aws", "File": "cfg.env", "StartLine": 2, "Description": "AWS key",
                                                      "Fingerprint": "abc123:cfg.env:aws:2"}]))
        [f] = analyze.parse_gitleaks("", self.root, self.tmp)
        self.assertIn("abc123:cfg.env:aws:2", f.message)

    def test_gitleaks_runs_on_working_tree_and_history(self):
        runs = [t for t in analyze.TOOLS if t.binary == "gitleaks"]
        self.assertEqual([t.argv("gitleaks", self.root, self.tmp)[1] for t in runs], ["dir", "git"])
        self.assertEqual([t.applies(self.root) for t in runs], [True, False])
        (self.root / ".git").mkdir()
        self.assertEqual([t.applies(self.root) for t in runs], [True, True])

    def test_gitleaks_missing_report_is_clean(self):
        self.assertEqual(analyze.parse_gitleaks("", self.root, self.tmp), [])

    def test_osv(self):
        out = json.dumps({"results": [{"source": {"path": str(self.root / "package-lock.json")}, "packages": [
            {"package": {"name": "lodash", "version": "4.17.20"}, "vulnerabilities": [{"id": "GHSA-1", "summary": "proto pollution"}]}]}]})
        [f] = analyze.parse_osv(out, self.root, self.tmp)
        self.assertEqual((f.category, f.rule, f.path), ("dependency", "GHSA-1", "package-lock.json"))
        self.assertIn("lodash@4.17.20", f.message)

    def test_osv_empty(self):
        self.assertEqual(analyze.parse_osv("", self.root, self.tmp), [])

    def test_paths_outside_root_kept_as_given(self):
        self.assertEqual(analyze.rel("/elsewhere/x.py", self.root), "/elsewhere/x.py")
        self.assertEqual(analyze.rel(".\\src\\a.py" if os.name == "nt" else "./src/a.py", self.root), "src/a.py")


class Run(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.bindir = tree(self)
        self.tmp = tree(self)
        self.env = {"PATH": str(self.bindir)}

    def tool(self, name, parse, applies=lambda root: True, ok=(0, 1)):
        return analyze.Tool(name, "any", lambda exe, root, tmp: [exe], parse, applies, "install it", ok)

    def test_missing_tool_is_skipped(self):
        report = analyze.run_tools([self.tool("ghost", analyze.parse_mypy)], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual(report.skipped, [("ghost", "not installed; install it")])

    def test_not_applicable_is_skipped_with_reason(self):
        fake_tool(self.bindir, "mypy")
        t = analyze.Tool("mypy", "python", lambda exe, root, tmp: [exe], analyze.parse_mypy, lambda root: False, "x", (0, 1), "no mypy config")
        report = analyze.run_tools([t], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual(report.skipped, [("mypy", "no mypy config")])

    def test_other_stack_is_silent(self):
        t = analyze.Tool("tsc", "node", lambda exe, root, tmp: [exe], analyze.parse_tsc, lambda root: True, "x", (0, 1))
        report = analyze.run_tools([t], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual((report.skipped, report.errors, report.findings), ([], [], []))

    def test_findings_with_nonzero_exit(self):
        fake_tool(self.bindir, "mypy", "a.py:1: error: bad  [misc]\n", code=1)
        report = analyze.run_tools([self.tool("mypy", analyze.parse_mypy)], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.errors, [])

    def test_a_failure_exit_is_an_error_even_when_findings_parsed(self):
        fake_tool(self.bindir, "mypy", "a.py:1: error: bad  [misc]\n", code=2)
        write(self.root / "mypy.ini", "[mypy]\n")
        [mypy] = [t for t in analyze.TOOLS if t.name == "mypy"]
        report = analyze.run_tools([mypy], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual(len(report.findings), 1)
        self.assertIn("exit 2", report.errors[0][1])
        fake_tool(self.bindir, "mypy", "a.py:1: error: bad  [misc]\n", code=1)
        report = analyze.run_tools([mypy], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual((len(report.findings), report.errors), (1, []))

    def test_a_partial_parse_keeps_findings_and_reports_the_error(self):
        out = json.dumps({"results": [{"check_id": "r.sql", "path": "a.py", "start": {"line": 3}, "extra": {}}], "errors": [{"message": "rule crashed"}]})
        fake_tool(self.bindir, "semgrep", out)
        report = analyze.run_tools([self.tool("semgrep", analyze.parse_semgrep)], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual([f.rule for f in report.findings], ["r.sql"])
        self.assertIn("rule crashed", report.errors[0][1])

    def test_unexpected_exit_without_findings_is_error(self):
        fake_tool(self.bindir, "mypy", "", code=3)
        report = analyze.run_tools([self.tool("mypy", analyze.parse_mypy)], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual(len(report.errors), 1)
        self.assertIn("exit 3", report.errors[0][1])
        self.assertIn("stderr of mypy", report.errors[0][1])

    def test_parse_failure_is_error_not_crash(self):
        fake_tool(self.bindir, "ruff", "not json")
        report = analyze.run_tools([self.tool("ruff", analyze.parse_ruff)], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual(len(report.errors), 1)
        self.assertIn("unreadable output", report.errors[0][1])

    def test_default_ok_is_zero_only(self):
        fake_tool(self.bindir, "mypy", "", code=1)
        t = analyze.Tool("mypy", "any", lambda exe, root, tmp: [exe], analyze.parse_mypy)
        report = analyze.run_tools([t], self.root, {"python"}, path=str(self.bindir))
        self.assertIn("exit 1", report.errors[0][1])

    def test_timeout_is_error(self):
        fake_tool(self.bindir, "mypy", "", sleep=5)
        report = analyze.run_tools([self.tool("mypy", analyze.parse_mypy)], self.root, {"python"}, path=str(self.bindir), timeout=1)
        self.assertIn("timed out", report.errors[0][1])

    def test_opt_outs_reach_the_tool(self):
        fake_tool(self.bindir, "envdump", "")
        (self.bindir / "envdump_impl.py").write_text("import json, os, sys\nprint(json.dumps(dict(os.environ)))\n", encoding="utf-8")
        seen = {}

        def grab(out, root, tmp):
            seen.update(json.loads(out))
            return []
        analyze.run_tools([self.tool("envdump", grab)], self.root, {"python"}, path=str(self.bindir))
        for key, value in analyze.TOOL_ENV.items():
            self.assertEqual(seen.get(key), value)
        self.assertEqual(seen.get("PYTHONUTF8"), "1")

    def test_timeout_kills_the_whole_process_tree(self):
        marker = self.tmp / "grandchild-alive"
        grandchild = f"import pathlib, time; time.sleep(4); pathlib.Path({str(marker)!r}).write_text('x')"
        fake_tool(self.bindir, "mypy", body=textwrap.dedent(f'''\
            import subprocess, sys, time
            subprocess.Popen([sys.executable, "-c", {grandchild!r}])
            time.sleep(60)
        '''))
        started = time.monotonic()
        report = analyze.run_tools([self.tool("mypy", analyze.parse_mypy)], self.root, {"python"}, path=str(self.bindir), timeout=1)
        self.assertLess(time.monotonic() - started, 20)
        self.assertIn("timed out", report.errors[0][1])
        time.sleep(6)
        self.assertFalse(marker.exists())

    def test_findings_outside_the_repo_or_in_build_dirs_are_dropped(self):
        rows = [analyze.Finding("bug", "t", "r", path, 1, "m") for path in
                ("src/a.py", "/home/u/.cargo/registry/x.rs", "src-tauri/target/debug/x.rmeta", "vendor/lib/a.go", "targets/a.py")]
        fake_tool(self.bindir, "mypy", "")
        t = analyze.Tool("mypy", "any", lambda exe, root, tmp: [exe], lambda out, root, tmp: rows, ok=(0,))
        report = analyze.run_tools([t], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual([f.path for f in report.findings], ["src/a.py", "targets/a.py"])

    def test_gitleaks_config_allows_only_the_ignored_paths(self):
        config = analyze._gitleaks_config(["node_modules/", ".env", "a.b/"])
        self.assertIn("useDefault = true", config)
        self.assertIn(r"(^|/)(node_modules/|\.env$|a\.b/)", config)

    def test_ignored_paths_come_from_git_and_are_empty_outside_a_repo(self):
        self.assertEqual(analyze._ignored_paths(self.root), [])
        git(self.root, "init", "-q")
        write(self.root / ".gitignore", "dist/\n")
        write(self.root / "dist" / "a.js", "x")
        self.assertEqual(analyze._ignored_paths(self.root), ["dist/"])
        self.assertEqual(analyze._ignored_paths(self.root, limit=0), [])

    def test_dropped_findings_are_counted_and_shown(self):
        rows = [analyze.Finding("bug", "t", "r", path, 1, "m") for path in ("a.py", "vendor/b.py", "/abs/c.py")]
        fake_tool(self.bindir, "mypy", "")
        t = analyze.Tool("mypy", "any", lambda exe, root, tmp: [exe], lambda out, root, tmp: rows, ok=(0,))
        report = analyze.run_tools([t], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual(report.dropped, 2)
        self.assertIn("not shown: 2 findings", "\n".join(analyze.render(report, {"python"})))

    def test_secret_scanners_keep_tracked_files_in_build_dirs(self):
        git(self.root, "init", "-q")
        write(self.root / ".gitignore", "target/\n")
        write(self.root / "vendor" / "k.env", "x")
        write(self.root / "target" / "k.bin", "x")
        git(self.root, "add", ".gitignore", "vendor/k.env")
        rows = [analyze.Finding("secret", "gitleaks", "key", path, 1, "m") for path in ("vendor/k.env", "target/k.bin")]
        hist = [analyze.Finding("secret", "gitleaks", "key", "target/old.bin", 1, "m")]
        for name, found, want in (("gitleaks", rows, ["vendor/k.env"]), ("gitleaks-history", hist, ["target/old.bin"])):
            fake_tool(self.bindir, name, "")
            t = analyze.Tool(name, "any", lambda exe, root, tmp: [exe], lambda out, root, tmp, found=found: found, ok=(0,))
            report = analyze.run_tools([t], self.root, {"python"}, path=str(self.bindir) + os.pathsep + os.path.dirname(shutil.which("git")))
            self.assertEqual([f.path for f in report.findings], want, name)

    def test_lizard_crash_leaves_out_only_the_files_that_crash(self):
        write(self.root / "ok1.py", "x = 1\n")
        write(self.root / "ok2.py", "x = 2\n")
        write(self.root / "bad.go", "x\n")
        body = textwrap.dedent('''\
            import sys
            files = open(sys.argv[sys.argv.index("-f") + 1]).read().split()
            if "bad.go" in files:
                sys.stderr.write("Traceback (most recent call last):\\nAttributeError: boom\\n")
                sys.exit(1)
            print("9,8,51,1,9,\\"f@2-10@ok1.py\\",\\"ok1.py\\",\\"f\\",\\"f( x )\\",2,10,200")
        ''')
        fake_tool(self.bindir, "lizard", body=body)
        t = analyze.TOOLS[0]
        self.assertEqual(t.name, "lizard")
        with mock.patch.object(analyze, "source_files", return_value=["ok1.py", "ok2.py", "bad.go"]):
            report = analyze.run_tools([t], self.root, {"python"}, path=str(self.bindir))
        self.assertEqual([(n, "bad.go" in why) for n, why in report.errors], [("lizard", True)])
        self.assertEqual([f.rule for f in report.findings], ["cognitive-complexity"])

    def test_error_reason_skips_progress_lines(self):
        err = "go: downloading github.com/x/y v1.0.0\n# pkg\nvet: ./a.go:3:1: undefined: z\n"
        self.assertEqual(analyze._first(err), "vet: ./a.go:3:1: undefined: z")
        self.assertEqual(analyze._first("# only noise\n"), "")

    def test_lineless_findings_with_different_messages_are_kept(self):
        proj = "Api/Api.csproj"
        out = f"{proj} : warning NU1903: Package 'A' 1.0 is vulnerable\n{proj} : warning NU1903: Package 'B' 2.0 is vulnerable\n"
        fake_tool(self.bindir, "dotnet", out)
        t = analyze.Tool("dotnet", "any", lambda exe, root, tmp: [exe], analyze.parse_dotnet)
        found = analyze.run_tools([t], self.root, {"dotnet"}, path=str(self.bindir)).findings
        self.assertEqual(sorted(f.message for f in found), ["Package 'A' 1.0 is vulnerable", "Package 'B' 2.0 is vulnerable"])

    def test_same_finding_from_two_runs_is_reported_once(self):
        fake_tool(self.bindir, "mypy", "a.py:1: error: bad  [misc]\n", code=1)
        tools = [self.tool("mypy", analyze.parse_mypy), self.tool("mypy", analyze.parse_mypy)]
        self.assertEqual(len(analyze.run_tools(tools, self.root, {"python"}, path=str(self.bindir)).findings), 1)

    def test_tmp_is_removed(self):
        made = []

        def grab(out, root, tmp):
            made.append(tmp)
            return []
        fake_tool(self.bindir, "mypy", "")
        analyze.run_tools([self.tool("mypy", grab)], self.root, {"python"}, path=str(self.bindir))
        self.assertFalse(made[0].exists())


class Changed(unittest.TestCase):
    def setUp(self):
        self.repo = tree(self) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        write(self.repo / "old.py", "x = 1\n")
        write(self.repo / "gone.py", "y = 1\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "checkout", "-q", "-b", "feature")
        write(self.repo / "new dir" / "ação.py", "z = 1\n")
        write(self.repo / "old.py", "x = 2\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "work")
        write(self.repo / "untracked.py", "u = 1\n")
        (self.repo / "gone.py").unlink()

    def test_changed_files(self):
        self.assertEqual(analyze.changed(self.repo, "main"), {"old.py", "new dir/ação.py", "untracked.py", "gone.py"})

    def test_changed_from_subdirectory(self):
        self.assertEqual(analyze.changed(self.repo / "new dir", "main"), {"ação.py"})

    def test_bad_base(self):
        with self.assertRaisesRegex(ValueError, "nope"):
            analyze.changed(self.repo, "nope")

    def test_a_failing_git_listing_is_an_error_not_an_empty_set(self):
        real = analyze._git
        for failing in ("diff", "ls-files"):
            def fake(root, *args, failing=failing):
                if args[0] == failing:
                    return subprocess.CompletedProcess(args, 128, "", "fatal: index file corrupt\n")
                return real(root, *args)
            with self.subTest(failing=failing), mock.patch.object(analyze, "_git", fake), \
                    self.assertRaisesRegex(ValueError, "index file corrupt"):
                analyze.changed(self.repo, "main")


class Render(unittest.TestCase):
    def test_summary(self):
        f = [analyze.Finding("security", "ruff", "S602", "a.py", 9, "shell\x1b[31m=True"),
             analyze.Finding("complexity", "lizard", "cognitive-complexity", "b.py", 0, "f is complex")]
        report = analyze.Report(f, [("mypy", "no mypy config")], [("tsc", "exit 3: boom")])
        text = "\n".join(analyze.render(report, {"python"}, top=1))
        self.assertIn("security 1", text)
        self.assertIn("unused 0", text)
        self.assertIn("a.py:9  S602  shell\\x1b[31m=True", text)
        self.assertIn("b.py  cognitive-complexity", text)
        self.assertIn("skipped: mypy (no mypy config)", text)
        self.assertIn("error: tsc: exit 3: boom", text)

    def test_top_limit(self):
        f = [analyze.Finding("bug", "ruff", "B1", "a.py", i, "m") for i in range(1, 5)]
        text = "\n".join(analyze.render(analyze.Report(f, [], []), {"python"}, top=2))
        self.assertIn("and 2 more", text)


class Cli(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.bindir = tree(self)
        self.old_path = os.environ.get("PATH", "")
        launcher(self.bindir, "git", [shutil.which("git")])
        os.environ["PATH"] = str(self.bindir)
        self.addCleanup(os.environ.__setitem__, "PATH", self.old_path)
        self.out = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def args(self, **kw):
        return types.SimpleNamespace(path=str(self.root), base=None, top=10, json=False, timeout=60, **kw)

    def test_no_stack(self):
        self.assertEqual(analyze.cli(self.args()), 2)

    def test_clean_run_exits_zero(self):
        write(self.root / "tool.py", "x = 1\n")
        fake_tool(self.bindir, "ruff", "[]")
        self.assertEqual(analyze.cli(self.args()), 0)

    def test_findings_exit_one_and_json(self):
        write(self.root / "tool.py", "x = 1\n")
        fake_tool(self.bindir, "lizard", LIZARD_CSV)
        args = self.args()
        args.json = True
        self.assertEqual(analyze.cli(args), 1)
        data = json.loads(self.out.getvalue())
        self.assertIn("cognitive-complexity", {f["rule"] for f in data["findings"]})

    def test_nothing_ran_exits_two(self):
        write(self.root / "tool.py", "x = 1\n")
        self.assertEqual(analyze.cli(self.args()), 2)

    def test_narrow_console_encoding_does_not_crash(self):
        write(self.root / "tool.py", "x = 1\n")
        fake_tool(self.bindir, "ruff", json.dumps([{"code": "B1", "message": "łódź ação", "filename": "tool.py", "location": {"row": 1}}]))
        narrow = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with contextlib.redirect_stdout(narrow):
            self.assertEqual(analyze.cli(self.args()), 1)
            args = self.args()
            args.json = True
            self.assertEqual(analyze.cli(args), 1)

    def test_bad_base_exits_two(self):
        write(self.root / "tool.py", "x = 1\n")
        git(self.root, "init", "-q")
        args = self.args()
        args.base = "nope"
        self.assertEqual(analyze.cli(args), 2)


RUST_LIB = textwrap.dedent('''\
    pub fn first(v: &[u32]) -> u32 {
        v.iter().max().unwrap() + v[0]
    }

    pub fn boom() {
        panic!("x")
    }

    pub fn narrow(x: u64) -> u32 {
        x as u32
    }

    pub fn read(p: *const u8) -> u8 {
        unsafe { *p }
    }

    pub fn style() -> u32 {
        return 1;
    }

    pub fn ex(o: Option<u32>) -> u32 {
        o.expect("x")
    }

    pub fn unr() {
        unreachable!()
    }

    #[cfg(test)]
    mod tests {
        #[test]
        fn inside() {
            let v = vec![1];
            v.iter().max().unwrap();
            let _ = v[0];
            let _ = 5u64 as u32;
            let _ = (-1i32) as u32;
            unreachable!();
            panic!("fine in tests");
        }
    }
''')
RUST_IT = "pub fn helper(v: &[u32]) -> u32 {\n    v.iter().max().unwrap() + v[0]\n}\n"


def rust_crate(test: unittest.TestCase, manifest: str = "", lib: str = RUST_LIB) -> Path:
    root = tree(test)
    write(root / "Cargo.toml", '[package]\nname = "fx"\nversion = "0.1.0"\nedition = "2021"\n' + manifest)
    write(root / "src" / "lib.rs", lib)
    write(root / "tests" / "it.rs", RUST_IT)
    target = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, target, True)
    patch = mock.patch.dict(os.environ, {"CARGO_TARGET_DIR": str(target)})
    patch.start()
    test.addCleanup(patch.stop)
    return root


def clippy_findings(root: Path, strict: bool = False) -> analyze.Report:
    return analyze.run_tools([analyze.clippy_tool(strict)], root, {"rust"})


@unittest.skipUnless(shutil.which("cargo"), "cargo not installed")
class RustClippy(unittest.TestCase):
    def rules(self, report):
        return {(f.category, f.rule, f.path) for f in report.findings}

    def lines(self, report, rule):
        return sorted(f.line for f in report.findings if f.rule == rule)

    def test_default_tier_and_test_code(self):
        report = clippy_findings(rust_crate(self))
        self.assertEqual(report.errors, [])
        got = self.rules(report)
        for expected in (("bug", "clippy::unwrap_used", "src/lib.rs"), ("bug", "clippy::panic", "src/lib.rs"),
                         ("bug", "clippy::needless_return", "src/lib.rs"), ("security", "clippy::undocumented_unsafe_blocks", "src/lib.rs")):
            self.assertIn(expected, got)
        rules = {f.rule for f in report.findings}
        self.assertFalse(rules & {"clippy::indexing_slicing", "clippy::cast_possible_truncation", "clippy::cast_sign_loss", "clippy::expect_used",
                                  "clippy::unreachable", "clippy::arithmetic_side_effects"})
        self.assertEqual(self.lines(report, "clippy::unwrap_used"), [2])
        self.assertFalse([f for f in report.findings if f.path.startswith("tests/")])

    def test_strict_tier_adds_noisy_lints_but_not_from_test_code(self):
        report = clippy_findings(rust_crate(self), strict=True)
        src = RUST_LIB.splitlines()
        first_test = next(n for n, ln in enumerate(src, 1) if ln.strip() == "#[cfg(test)]")
        for rule in ("clippy::indexing_slicing", "clippy::cast_possible_truncation", "clippy::expect_used", "clippy::unreachable"):
            lines = self.lines(report, rule)
            self.assertTrue(lines, rule)
            self.assertTrue(all(n < first_test for n in lines), (rule, lines))
        self.assertEqual(self.lines(report, "clippy::cast_sign_loss"), [])
        self.assertFalse([f for f in report.findings if f.path.startswith("tests/")])

    def test_arithmetic_only_when_strict(self):
        lib = "pub fn add(a: u32, b: u32) -> u32 {\n    a + b\n}\n"
        root = rust_crate(self, lib=lib)
        self.assertNotIn("clippy::arithmetic_side_effects", {f.rule for f in clippy_findings(root).findings})
        self.assertIn("clippy::arithmetic_side_effects", {f.rule for f in clippy_findings(root, strict=True).findings})

    def test_arithmetic_when_manifest_asks(self):
        lib = "pub fn add(a: u32, b: u32) -> u32 {\n    a + b\n}\n"
        root = rust_crate(self, "[package.metadata.code-jig]\nstrict = true\n", lib)
        self.assertIn("clippy::arithmetic_side_effects", {f.rule for f in clippy_findings(root).findings})

    def test_project_lints_are_honored(self):
        root = rust_crate(self, "[lints.clippy]\nunwrap_used = \"allow\"\n")
        rules = {f.rule for f in clippy_findings(root).findings}
        self.assertNotIn("clippy::unwrap_used", rules)

    def test_project_clippy_toml_is_not_overridden(self):
        root = rust_crate(self)
        write(root / "clippy.toml", "too-many-arguments-threshold = 20\n")
        self.assertEqual(analyze._clippy_env(root, root), {})

    def test_flags_without_project_lints(self):
        root = rust_crate(self)
        argv = analyze.clippy_tool().argv("cargo", root, root)
        self.assertNotIn("clippy::all", argv)
        self.assertIn("clippy::unwrap_used", argv)
        self.assertNotIn("clippy::arithmetic_side_effects", argv)
        self.assertNotIn("clippy::indexing_slicing", argv)
        self.assertIn("clippy::indexing_slicing", analyze.clippy_tool(True).argv("cargo", root, root))
        self.assertIn("clippy::arithmetic_side_effects", analyze.clippy_tool(True).argv("cargo", root, root))


@unittest.skipUnless(shutil.which("cargo"), "cargo not installed")
class RustBuildScope(unittest.TestCase):
    GATED = '#[cfg(feature = "sim")]\npub fn gated(v: &[u32]) -> u32 {\n    *v.first().unwrap()\n}\n'

    def test_all_features_reach_gated_code(self):
        root = rust_crate(self, "[features]\nsim = []\n", self.GATED)
        report = clippy_findings(root)
        self.assertEqual(report.errors, [])
        self.assertIn(("clippy::unwrap_used", 3), {(f.rule, f.line) for f in report.findings})

    def test_conflicting_features_fall_back_to_default(self):
        lib = '#[cfg(all(feature = "a", feature = "b"))]\ncompile_error!("a and b conflict");\n\npub fn f(v: &[u32]) -> u32 {\n    *v.first().unwrap()\n}\n'
        root = rust_crate(self, "[features]\na = []\nb = []\n", lib)
        report = clippy_findings(root)
        self.assertEqual([r for _, r in report.errors], [analyze.clippy_tool().fallback_note])
        self.assertIn("clippy::unwrap_used", {f.rule for f in report.findings})
        self.assertFalse([f for f in report.findings if f.category == "type"])

    def test_no_features_no_flag(self):
        argv = analyze.clippy_tool().argv("cargo", rust_crate(self), Path())
        self.assertNotIn("--all-features", argv)
        self.assertIn("--offline", argv)
        self.assertNotIn("--target", argv)

    def test_workspace_covers_every_member(self):
        root = tree(self)
        write(root / "Cargo.toml", '[workspace]\nresolver = "2"\nmembers = ["a", "b"]\n')
        for name in "ab":
            write(root / name / "Cargo.toml", f'[package]\nname = "m{name}"\nversion = "0.1.0"\nedition = "2021"\n')
            write(root / name / "src" / "lib.rs", "pub fn f(v: &[u32]) -> u32 {\n    *v.first().unwrap()\n}\n")
        target = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, target, True)
        with mock.patch.dict(os.environ, {"CARGO_TARGET_DIR": str(target)}):
            report = clippy_findings(root)
        self.assertEqual(report.errors, [])
        self.assertEqual(sorted(f.path for f in report.findings if f.rule == "clippy::unwrap_used"), ["a/src/lib.rs", "b/src/lib.rs"])

    def test_installed_config_target_is_kept(self):
        root = rust_crate(self)
        host = analyze._host_triple(root)
        write(root / ".cargo" / "config.toml", f'[build]\ntarget = "{host}"\n')
        argv = analyze.clippy_tool().argv("cargo", root, Path())
        self.assertNotIn("--target", argv)
        self.assertIsNone(analyze._clippy_note(root))

    def test_uninstalled_config_target_falls_back_to_host_and_says_so(self):
        root = rust_crate(self)
        write(root / ".cargo" / "config.toml", '[build]\ntarget = "thumbv7em-none-eabi"\n')
        with mock.patch.object(analyze, "_target_installed", return_value=False):
            argv = analyze.clippy_tool().argv("cargo", root, Path())
            note = analyze._clippy_note(root)
        self.assertEqual(argv[argv.index("--target") + 1], analyze._host_triple(root))
        self.assertIn("thumbv7em-none-eabi", note)
        self.assertIn("rustup target add", note)

    def test_note_reaches_the_report(self):
        root = rust_crate(self)
        write(root / ".cargo" / "config.toml", '[build]\ntarget = "thumbv7em-none-eabi"\n')
        report = clippy_findings(root)
        self.assertEqual([t for t, _ in report.errors], ["clippy"])
        self.assertIn("thumbv7em-none-eabi", report.errors[0][1])
        self.assertIn("clippy::unwrap_used", {f.rule for f in report.findings})

    def test_installed_target_is_detected_in_the_sysroot(self):
        root = rust_crate(self)
        self.assertTrue(analyze._target_installed(analyze._host_triple(root), root))
        self.assertFalse(analyze._target_installed("nope-unknown-none", root))

    def test_metadata_target_wins(self):
        root = rust_crate(self, '[package.metadata.code-jig]\ntarget = "x86_64-unknown-linux-gnu"\n')
        argv = analyze.clippy_tool().argv("cargo", root, Path())
        self.assertEqual(argv[argv.index("--target") + 1], "x86_64-unknown-linux-gnu")


class RustSupplyChain(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.tmp = self.root
        write(self.root / "Cargo.toml", '[package]\nname = "fx"\n\n[dependencies]\nserde = "1"\nlog = "0.4"\n')

    def test_cargo_audit(self):
        advisory = {"id": "RUSTSEC-2020-0071", "title": "Potential segfault in time"}
        out = json.dumps({"vulnerabilities": {"found": True, "count": 1, "list": [{"advisory": advisory, "package": {"name": "time", "version": "0.1.43"}}]},
                          "warnings": {"unmaintained": [{"kind": "unmaintained", "advisory": {"id": "RUSTSEC-2021-0139", "title": "ansi_term is unmaintained"},
                                                         "package": {"name": "ansi_term", "version": "0.12.1"}}], "yanked": []}})
        found = analyze.parse_cargo_audit(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.tool, f.rule, f.path, f.line, f.message) for f in found], [
            ("dependency", "cargo-audit", "RUSTSEC-2020-0071", "Cargo.lock", 0, "time@0.1.43: Potential segfault in time"),
            ("dependency", "cargo-audit", "RUSTSEC-2021-0139", "Cargo.lock", 0, "ansi_term@0.12.1: ansi_term is unmaintained")])

    def test_cargo_audit_needs_a_lockfile_and_a_local_advisory_db(self):
        home = self.root / "cargo home"
        with mock.patch.dict(os.environ, {"CARGO_HOME": str(home)}):
            self.assertFalse(analyze._audit_ready(self.root))
            write(self.root / "Cargo.lock", "")
            self.assertFalse(analyze._audit_ready(self.root))
            (home / "advisory-db").mkdir(parents=True)
            self.assertTrue(analyze._audit_ready(self.root))

    def test_cargo_machete(self):
        out = ("Analyzing dependencies of crates in this directory...\ncargo-machete found the following unused dependencies in this directory:\n"
               f"fx -- {self.root / 'Cargo.toml'}:\n\tlog\n\tserde\n")
        found = analyze.parse_cargo_machete(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.tool, f.rule, f.path, f.line) for f in found], [
            ("unused", "cargo-machete", "unused-dependency", "Cargo.toml", 6), ("unused", "cargo-machete", "unused-dependency", "Cargo.toml", 5)])

    def test_cargo_deny(self):
        def diag(severity, code, message):
            return json.dumps({"type": "diagnostic", "fields": {"code": code, "message": message, "severity": severity, "labels": []}})
        out = "\n".join([diag("error", "vulnerability", "time 0.1.43 is vulnerable"), diag("warning", "unmaintained", "ansi_term is unmaintained"),
                         diag("note", "license-not-encountered", "skip"), json.dumps({"type": "summary", "fields": {}}), "plain text"])
        found = analyze.parse_cargo_deny(out, self.root, self.tmp)
        self.assertEqual([(f.category, f.rule, f.message) for f in found], [
            ("dependency", "vulnerability", "time 0.1.43 is vulnerable"), ("dependency", "unmaintained", "ansi_term is unmaintained")])

    def test_missing_tools_are_skipped_with_a_hint(self):
        empty = self.root / "empty"
        empty.mkdir()
        wanted = [t for t in analyze.TOOLS if t.name in ("cargo-audit", "cargo-machete", "cargo-deny")]
        write(self.root / "Cargo.lock", "")
        report = analyze.run_tools(wanted, self.root, {"rust"}, path=str(empty))
        self.assertEqual(report.errors, [])
        self.assertEqual(report.ran, [])
        self.assertEqual({n for n, _ in report.skipped}, {"cargo-audit", "cargo-machete", "cargo-deny"})
        self.assertIn("deny.toml", dict(report.skipped)["cargo-deny"])
        self.assertIn("cargo install cargo-machete", dict(report.skipped)["cargo-machete"])

    def test_cargo_deny_runs_only_with_a_deny_toml(self):
        deny = next(t for t in analyze.TOOLS if t.name == "cargo-deny")
        self.assertFalse(deny.applies(self.root))
        write(self.root / "deny.toml", "")
        self.assertTrue(deny.applies(self.root))
        self.assertTrue(deny.stderr)

    def test_stderr_tools_parse_stderr(self):
        script = self.root / "fake.py"
        write(script, "import sys\nsys.stderr.write('{\"type\": \"diagnostic\", \"fields\": {\"severity\": \"error\", \"code\": \"banned\", \"message\": \"m\"}}\\n')\nsys.exit(1)\n")
        tool = analyze.Tool("cargo-deny", "rust", lambda exe, root, tmp: [sys.executable, str(script)], analyze.parse_cargo_deny, findings_exit=(1,), stderr=True)
        found, error = analyze._run_one(tool, sys.executable, self.root, dict(os.environ), 60)
        self.assertEqual((error, [f.rule for f in found]), (None, ["banned"]))


class TestLineRanges(unittest.TestCase):
    def test_cfg_test_modules_test_fns_and_inner_attribute(self):
        src = "fn a() {}\n#[cfg(test)]\nmod t {\n    #[test]\n    fn b() { 1 }\n}\n#[test]\nfn c() { 2 }\n#[cfg(not(test))]\nfn d() {}\n"
        self.assertEqual(unsafe_scan.test_line_ranges(src), [(2, 6), (4, 5), (7, 8)])
        self.assertEqual(unsafe_scan.test_line_ranges("#![cfg(test)]\nfn a() {}\n"), [(1, 2)])

    def test_strings_with_braces_do_not_end_the_item(self):
        src = '#[cfg(test)]\nmod t {\n    const S: &str = "}";\n    fn f() {}\n}\nfn after() {}\n'
        self.assertEqual(unsafe_scan.test_line_ranges(src), [(1, 5)])

    def test_findings_in_cfg_test_code_are_dropped(self):
        root = tree(self)
        write(root / "Cargo.toml", "")
        write(root / "src" / "lib.rs", "fn a() {}\n#[cfg(test)]\nmod t {\n    fn b() { 1u64 as u32; }\n}\n")
        def msg(line):
            return json.dumps({"reason": "compiler-message", "message": {"level": "warning", "message": "m", "code": {"code": "clippy::cast_possible_truncation"},
                                                                       "spans": [{"file_name": "src/lib.rs", "line_start": line, "is_primary": True}]}})
        found = analyze.parse_clippy(msg(4) + "\n" + msg(1), root, root)
        self.assertEqual([f.line for f in found], [1])


class UnsafeScan(unittest.TestCase):
    SRC = textwrap.dedent('''\
        fn a(p: *const u8) -> u8 {
            // SAFETY: caller passes a valid pointer
            unsafe { *p }
        }
        fn b(p: *const u8) -> u8 {
            unsafe { *p }
        }
        fn c(p: *const u8) -> u8 {
            unsafe {
                // Safety: checked above
                *p
            }
        }
        fn d<'a>(p: &'a str) -> &'a str {
            let _ = "unsafe { not code }";
            let _ = r#"unsafe { " still a string }"#;
            let _ = '\\'';
            // unsafe { in a comment }
            /* unsafe { /* nested */ } */
            p
        }
        unsafe fn e() {}
        unsafe impl Send for T {}
        fn f(p: *const u8) -> u8 {
            unsafe { *p }
        }
    ''')

    def test_counts_and_undocumented_lines(self):
        self.assertEqual(unsafe_scan.undocumented(self.SRC), (6, [6, 23, 25]))

    def test_unsafe_in_strings_and_comments_is_not_counted(self):
        self.assertEqual(unsafe_scan.undocumented('let s = "unsafe {";\n// unsafe {\n'), (0, []))

    def test_non_ascii_identifiers_do_not_crash(self):
        self.assertEqual(unsafe_scan.undocumented("fn \u00e9() { let \u00f1ame = 1; unsafe { } }\n"), (1, [1]))
        self.assertEqual(unsafe_scan.undocumented("let \u00e9unsafe = 1;\n"), (0, []))

    def test_unsafe_inside_literals_and_nested_comments_is_ignored(self):
        src = 'let a = r#"unsafe { "#;\nlet b = br"unsafe {";\nlet c = b"unsafe {";\n/* /* unsafe { */ unsafe { */\n'
        self.assertEqual(unsafe_scan.undocumented(src), (0, []))

    def test_comments_between_unsafe_and_brace(self):
        self.assertEqual(unsafe_scan.undocumented("unsafe /* c */ { }\n"), (1, [1]))
        self.assertEqual(unsafe_scan.undocumented("unsafe\n// c\n{ }\n"), (1, [1]))
        self.assertEqual(unsafe_scan.undocumented("// SAFETY: ok\nunsafe /* c */ { }\n"), (1, []))

    def test_declarations_are_counted_not_flagged(self):
        self.assertEqual(unsafe_scan.undocumented("unsafe fn f() {}\nunsafe trait T {}\nunsafe extern \"C\" fn g() {}\n"), (3, []))

    def test_extern_block_and_impl_need_safety(self):
        self.assertEqual(unsafe_scan.undocumented('unsafe extern "C" { fn f(); }\nunsafe impl Send for T {}\n'), (2, [1, 2]))
        self.assertEqual(unsafe_scan.undocumented('// SAFETY: audited\nunsafe impl Send for T {}\n'), (1, []))

    def test_only_a_safety_label_counts(self):
        self.assertEqual(unsafe_scan.undocumented("// no safety concerns here\nunsafe { }\n"), (1, [2]))
        self.assertEqual(unsafe_scan.undocumented("// SAFETY: fine\n\n\n\n\nlet x = unsafe { };\n"), (1, []))
        self.assertEqual(unsafe_scan.undocumented("fn f() {\n    // SAFETY: fine\n    let x = unsafe { };\n}\n"), (1, []))
        self.assertEqual(unsafe_scan.undocumented("// SAFETY: old\nfn f() { }\nunsafe { }\n"), (1, [3]))

    def test_comment_right_after_the_brace(self):
        self.assertEqual(unsafe_scan.undocumented("unsafe {\n    // SAFETY: fine\n    f()\n}\n"), (1, []))

    def test_inline_tool_failure_is_an_error_not_a_crash(self):
        def boom(root):
            raise ValueError("bad")
        tool = analyze.Tool("unsafe-scan", "rust", lambda exe, root, tmp: [], lambda out, root, tmp: [], inline=boom)
        report = analyze.run_tools([tool], tree(self), {"rust"})
        self.assertEqual(report.errors, [("unsafe-scan", "failed: bad")])

    def test_clippy_hits_are_not_repeated(self):
        root = rust_crate(self, lib=self.SRC)
        with mock.patch.dict(os.environ, {}):
            report = analyze.run_tools([analyze.clippy_tool(), *[t for t in analyze.TOOLS if t.name == "unsafe-scan"]], root, {"rust"})
        by_line = [(f.path, f.line) for f in report.findings if f.category == "security"]
        self.assertEqual(len(by_line), len(set(by_line)))

    def test_tool_reports_low_security_per_block(self):
        root = rust_crate(self, lib=self.SRC)
        report = analyze.run_tools([t for t in analyze.TOOLS if t.name == "unsafe-scan"], root, {"rust"})
        self.assertEqual(report.errors, [])
        self.assertEqual([(f.category, f.rule, f.path, f.line) for f in report.findings], [("security", "undocumented-unsafe", "src/lib.rs", n) for n in (6, 23, 25)])
        self.assertIn("low", report.findings[0].message)

    def test_tool_runs_without_any_binary_on_the_path(self):
        root = tree(self)
        write(root / "Cargo.toml", "")
        write(root / "src" / "main.rs", "fn main() { unsafe { } }\n")
        report = analyze.run_tools([t for t in analyze.TOOLS if t.name == "unsafe-scan"], root, {"rust"}, path=str(root))
        self.assertEqual(report.ran, ["unsafe-scan"])
        self.assertEqual(len(report.findings), 1)


class ClippyCategories(unittest.TestCase):
    def test_unsafe_lints_are_security(self):
        self.assertEqual(analyze._clippy_category("clippy::missing_safety_doc", "warning"), "security")

    def test_panic_lint_in_tests_dir_dropped(self):
        root = tree(self)
        line = json.dumps({"reason": "compiler-message", "message": {"level": "warning", "message": "m", "code": {"code": "clippy::unwrap_used"},
                                                                   "spans": [{"file_name": "benches/b.rs", "line_start": 3, "is_primary": True}]}})
        self.assertEqual(analyze.parse_clippy(line, root, root), [])


@unittest.skipUnless(os.environ.get("CODE_JIG_REAL_TOOLS"), "set CODE_JIG_REAL_TOOLS=1 to run the real-tool tests")
class RealTools(unittest.TestCase):
    def test_real_lizard_and_ruff(self):
        root = tree(self)
        body = "def f(x):\n" + "".join("    " * (i + 1) + f"if x > {i}:\n" for i in range(6)) + "    " * 7 + "return x\n    return 0\n"
        write(root / "pyproject.toml", "")
        write(root / "a.py", "import subprocess\n" + body + "subprocess.call('ls', shell=True)\n")
        report = analyze.run_tools(analyze.TOOLS, root, {"python"}, path=os.environ["PATH"])
        self.assertEqual(report.errors, [])
        rules = {f.rule for f in report.findings}
        self.assertIn("cognitive-complexity", rules)
        self.assertTrue(any(r.startswith("S") for r in rules))

    @unittest.skipUnless(shutil.which("osv-scanner"), "osv-scanner not installed")
    def test_real_osv_scanner_reads_cargo_lock(self):
        root = tree(self)
        write(root / "Cargo.toml", '[package]\nname = "fx"\nversion = "0.1.0"\n')
        write(root / "Cargo.lock", 'version = 3\n\n[[package]]\nname = "time"\nversion = "0.1.43"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n')
        report = analyze.run_tools([t for t in analyze.TOOLS if t.name == "osv-scanner"], root, {"rust"})
        self.assertEqual(report.errors, [])
        self.assertIn("RUSTSEC-2020-0071", {f.rule for f in report.findings})
        self.assertEqual({f.path for f in report.findings}, {"Cargo.lock"})

    @unittest.skipUnless(shutil.which("lizard"), "lizard not installed")
    def test_real_lizard_reads_rust(self):
        root = tree(self)
        body = "pub fn f(x: u32) -> u32 {\n" + "".join(f"    if x > {i} {{\n" for i in range(18)) + "        return 1;\n" + "    }\n" * 18 + "    0\n}\n"
        write(root / "Cargo.toml", "")
        write(root / "src" / "lib.rs", body)
        report = analyze.run_tools([t for t in analyze.TOOLS if t.name == "lizard"], root, {"rust"})
        self.assertEqual(report.errors, [])
        self.assertIn(("cyclomatic-complexity", "src/lib.rs"), {(f.rule, f.path) for f in report.findings})

    @unittest.skipUnless(shutil.which("vulture"), "vulture not installed")
    def test_real_vulture(self):
        root = tree(self)
        write(root / "pyproject.toml", "")
        write(root / "m.py", "import os\n\ndef used():\n    return 1\n\nprint(used())\n")
        write(root / "combine.py", "import json\n")
        write(root / "bin" / "skip.py", "import csv\n")
        report = analyze.run_tools([t for t in analyze.TOOLS if t.name == "vulture"], root, {"python"})
        self.assertEqual(report.errors, [])
        self.assertEqual(sorted((f.rule, f.path, f.line) for f in report.findings), [("unused-import", "combine.py", 1), ("unused-import", "m.py", 1)])

    @unittest.skipUnless(shutil.which("knip"), "knip not installed")
    def test_real_knip(self):
        root = tree(self)
        write(root / "package.json", json.dumps({"name": "x", "version": "1.0.0", "main": "index.js", "dependencies": {"left-pad": "1.3.0", "is-odd": "3.0.1"}}))
        write(root / "index.js", "const { a } = require('./lib');\nconsole.log(a);\n")
        write(root / "lib.js", "exports.a = 1;\nexports.b = 2;\n")
        write(root / "orphan.js", "module.exports = 3;\n")
        report = analyze.run_tools([t for t in analyze.TOOLS if t.name == "knip"], root, {"node"})
        self.assertEqual(report.errors, [])
        rules = {(f.rule, f.path) for f in report.findings}
        self.assertIn(("knip/files", "orphan.js"), rules)
        deps = sorted(f.message for f in report.findings if f.rule == "knip/dependencies")
        self.assertEqual(deps, ["dependencies: is-odd", "dependencies: left-pad"])

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks not installed")
    def test_real_gitleaks(self):
        root = tree(self)
        key = "AKIA" + "Q7Z2X4J6L3N5P2R7"
        write(root / "pyproject.toml", "")
        write(root / "settings.py", f'AWS_ACCESS_KEY_ID = "{key}"\n')
        git(root, "init", "-q")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "x")
        write(root / "local.py", f'KEY = "{key}"\n')
        tools = [t for t in analyze.TOOLS if t.binary == "gitleaks"]
        report = analyze.run_tools(tools, root, {"python"})
        self.assertEqual(report.errors, [])
        self.assertEqual({(f.category, f.path) for f in report.findings}, {("secret", "settings.py"), ("secret", "local.py")})
        self.assertNotIn(key, json.dumps([f.message for f in report.findings]))

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks not installed")
    def test_real_gitleaks_skips_git_ignored_folders_but_not_tracked_vendor(self):
        root = tree(self)
        key = "AKIA" + "Q7Z2X4J6L3N5P2R7"
        write(root / "pyproject.toml", "")
        write(root / ".gitignore", "node_modules/\ndist/\n")
        write(root / "vendor" / "lib.py", f'KEY = "{key}"\n')
        git(root, "init", "-q")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "x")
        write(root / "node_modules" / "dep.py", f'KEY = "{key}"\n')
        write(root / "dist" / "bundle.py", f'KEY = "{key}"\n')
        tools = [t for t in analyze.TOOLS if t.name == "gitleaks"]
        report = analyze.run_tools(tools, root, {"python"})
        self.assertEqual(report.errors, [])
        self.assertEqual([f.path for f in report.findings], ["vendor/lib.py"])

    @unittest.skipUnless(shutil.which("ruff"), "ruff not installed")
    def test_real_ruff_flags_assert_outside_tests_only(self):
        root = tree(self)
        write(root / "pyproject.toml", "")
        for rel in ("app/core.py", "tests/test_core.py", "pkg/test_x.py", "pkg/tests/helper.py", "conftest.py", "pkg/y_test.py"):
            write(root / rel, "def f(x):\n    assert x\n")
        tools = [t for t in analyze.TOOLS if t.name == "ruff"]
        report = analyze.run_tools(tools, root, {"python"})
        self.assertEqual(report.errors, [])
        self.assertEqual([(f.rule, f.path) for f in report.findings], [("S101", "app/core.py")])

    @unittest.skipUnless(shutil.which("osv-scanner"), "osv-scanner not installed")
    def test_real_osv_scanner(self):
        root = tree(self)
        write(root / "package.json", '{"name": "x", "version": "1.0.0", "dependencies": {"lodash": "4.17.20"}}')
        write(root / "package-lock.json", json.dumps({"name": "x", "version": "1.0.0", "lockfileVersion": 3, "requires": True, "packages": {
            "": {"name": "x", "version": "1.0.0", "dependencies": {"lodash": "4.17.20"}},
            "node_modules/lodash": {"version": "4.17.20", "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.20.tgz"}}}))
        tools = [t for t in analyze.TOOLS if t.name == "osv-scanner"]
        report = analyze.run_tools(tools, root, {"node"})
        self.assertEqual(report.errors, [])
        self.assertTrue(any(f.category == "dependency" and "lodash@4.17.20" in f.message for f in report.findings))
