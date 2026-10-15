# Watermark stripper

The harness automatically removes invisible Unicode characters and AI attribution text from every file you write or edit through Claude Code or Codex. This is a safety measure that prevents accidental commits of AI-generated watermarks.

## What it strips

### Invisible characters

The stripper removes Unicode characters that carry no visible meaning but are known to be injected by LLM outputs:

- **Zero-width characters**: U+200B, U+200C, U+200D (join controls)
- **Mathematical operators as punctuation**: U+2061-U+2064 (invisible operators)
- **Directional markers**: U+202A-U+202E (left-to-right, right-to-left, pop formatting)
- **Isolate markers**: U+2066-U+2069 (first strong, LTR/RTL isolate, pop)
- **Word joiner**: U+2060
- **Mongolian vowel separator**: U+180E
- **Zero-width no-break space (BOM alternative)**: U+FEFF
- **Soft hyphen**: U+00AD (deleted, not replaced)
- **Narrow no-break space and no-break space**: U+202F, U+00A0 (replaced with regular space)

### Attribution text

Lines containing only attribution are removed entirely:

- `Co-Authored-By: Claude…`, `Co-Authored-By: …Codex…`, `Co-Authored-By: …ChatGPT…`
- `Generated with [Claude Code]`, `Generated with Claude`, etc.
- `🤖 Generated with…`
- `ai-assisted` / `ai-generated` boilerplate lines

## How it is wired

### For Claude Code

When you write or edit a file, the harness wires a `PostToolUse` hook on the Write, Edit, MultiEdit, and NotebookEdit tools. This hook reads the tool's input JSON, extracts the file path, and runs the stripper on the file immediately after the tool completes.

### For Codex

Codex (version 0.162+) does not support per-tool PostToolUse hooks. The harness runs a `Stop` hook that fires at the end of each Codex session. This hook runs the stripper as a fallback sweep after all commands have completed. Thus, watermarks are removed from "every code add" only after the session ends, not immediately on apply.

## Files the stripper does NOT touch

- **Binary files**: no changes
- **Already clean files**: no rewrite, mtime unchanged
- **Visible characters**: em dashes, quotes, and all other visible Unicode are preserved

## Disabling the stripper

To disable the watermark stripper for Claude Code, remove the PostToolUse hooks with the status message `"codex-harness watermark"` from `~/.claude/settings.json`:

```bash
jq '.hooks.PostToolUse |= map(select(.hooks[0].statusMessage != "codex-harness watermark"))' ~/.claude/settings.json > /tmp/settings.json.tmp
mv /tmp/settings.json.tmp ~/.claude/settings.json
```

To disable for Codex, remove the Stop hook with status message `"codex-harness watermark"` from `~/.codex/hooks.json` (though the harness reinstall will re-add it).

## Running manually

To strip watermarks from a file or directory:

```bash
python3 -m harness hooks --hook-type claude-code < /dev/null  # triggers on stdin-provided file_path in a JSON payload
python3 -c "from harness.watermark import strip_watermark; strip_watermark('/path/to/file')"
```

## Implementation details

The stripper:
- Never rewrites a file if nothing matched (preserves mtime for build caches)
- Preserves CRLF line endings and UTF-8 BOM (if present at start)
- Preserves the original file's permissions (mode)
- Fails gracefully: errors are logged to stderr, but the hook always returns success
- Reports changes to stderr: when watermarks are stripped, the count per category is logged
  - Claude Code: also reports via JSON systemMessage in the hook output
- Refuses to follow symlinks outside the current working directory
- Runs in under 50 ms typical (O(n) scan)
