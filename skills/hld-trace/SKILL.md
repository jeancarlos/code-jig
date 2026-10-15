---
name: hld-trace
description: Use when the user asks whether the code follows the high-level design (HLD), which requirements have tests, which are untested, or wants tests linked to requirement or work item IDs.
---

# HLD trace

Requirements get IDs, tests cite them, and `harness trace` checks the links deterministically. Judging whether a test really proves its requirement stays with you.

## 1. Get the requirement IDs

Write them to a file, one per line, or as JSON (a list of IDs, or objects with an `id` field).

Before any `az` command below: the `azure-devops` extension (`az extension add --name azure-devops`), `az login` done in your own terminal, and defaults set with `az devops configure --defaults organization=<url> project=<name>`.

- Azure DevOps work items (child items of a feature or epic):

  ```
  az boards query --wiql "SELECT [System.Id] FROM WorkItems WHERE [System.Parent] = 1234" -o json > ids.json
  ```

- Azure DevOps wiki, when the HLD page lists IDs such as `REQ-12`:

  ```
  az devops wiki page show --wiki <wiki> --path "/Design/Login" --include-content --query page.content -o tsv > hld.md
  grep -oE "REQ-[0-9]+" hld.md | sort -u > ids.txt
  ```

  PowerShell: `Select-String -Path hld.md -Pattern "REQ-\d+" -AllMatches | ForEach-Object { $_.Matches.Value } | Sort-Object -Unique > ids.txt`.

- GitHub issues: `gh issue list --label requirement --json number --jq ".[].number" > ids.txt` (`--jq` is built into `gh`, so the line is the same in PowerShell).
- A Markdown HLD in the repo: the same `grep` as the wiki case.

When the source needs `az` or `gh` and `command -v az` (PowerShell: `Get-Command az`) finds nothing, do not install it: ask the user to paste the IDs or export the page, and continue from that file.

## 2. Tag the tests

For each requirement, search the test files for the names it uses (endpoint, function, field, error message) with `rg -i` (`grep -rni` where `rg` is missing; PowerShell: `Select-String`), read the matching tests, and add the requirement's tag to those whose assertions check it, in the form the framework below uses; tests written in step 4 get the tag as they are written. Default tag: `REQ-<id>`, anywhere in a test file, case-insensitive.

| Framework | Example |
|---|---|
| xUnit | `[Trait("Requirement", "REQ-1234")]` |
| NUnit | `[Property("Requirement", "REQ-1234")]` |
| MSTest | `[TestProperty("Requirement", "REQ-1234")]` |
| Jest, Vitest | `it("REQ-1234 rejects an expired token", ...)` |
| pytest | `@pytest.mark.req("REQ-1234")`, with the `req` marker registered in the pytest config |

Teams that already write Azure Boards links in tests can keep them: `--pattern "AB#{id}"`. The pattern is literal text with one `{id}` placeholder.

## 3. Run the trace

```
harness trace ids.txt                     # or ids.json, or - for stdin
harness trace ids.txt --path services/api
harness trace ids.txt --pattern "AB#{id}" --json
```

It reads test files that git tracks or would track (`tests/`, `__tests__/`, `*.test.ts`, `test_*.py`, `*Tests.cs`, `*.Tests/` projects and similar) and reports requirements with tests, `missing` requirements, and `unknown` IDs that tests cite but the list does not contain. Exit 0 when nothing is missing or unknown, 1 otherwise, 2 for unusable input.

## 4. Close the gaps

- Missing: write the test (the `regression-tests` skill), tagged.
- Unknown: the requirement was renamed or removed, or the tag has a typo. Ask before deleting a test.
- Covered: read each requirement next to its tests and confirm the assertions prove it. A tag on a test that checks something else is worse than no tag.

## 5. Report

One table: each requirement ID, `covered`, `missing` or `unknown`, the test files that cite it, and for covered ones whether the assertions prove it. List the tests tagged, the tests written, and any deletion still waiting for the user. Commit nothing; the user reviews the diff.
