# Runbook: watermark stripping and humanizing

After every file Claude Code or Codex writes, the harness cleans that file and tells you, and the agent, what it changed. Nothing runs on files the agent did not just write.

## When it runs

| Agent | Hook | Files it looks at |
|---|---|---|
| Claude Code | `PostToolUse`, matcher `Write\|Edit\|MultiEdit\|NotebookEdit`, in `~/.claude/settings.json` | `tool_input.file_path` / `notebook_path` |
| Codex | `PostToolUse` in `~/.codex/hooks.json` | `apply_patch` calls only: the `*** Add File:`, `*** Update File:` and `*** Move to:` targets of the patch argument |

Any other tool call, including one that only reads a file or writes text that looks like a patch, touches nothing. Both entries carry the status message `codex-harness watermark`; `harness install` replaces them in place and leaves your own hooks alone. Relative paths resolve against the `cwd` in the hook payload, and only regular files inside that directory are touched: symlinks, directories and paths that resolve outside it are skipped.

When something changed, the hook prints one JSON object with `systemMessage` (shown to you) and `hookSpecificOutput.additionalContext` (given to the model), for example `watermark: src/app.py: stripped 2 invisible chars, 1 attribution lines`, and logs the same line to stderr. A clean file produces no output and keeps its modification time. The hook always exits 0, so a failure never blocks the tool call.

## Watermarks

Every text file:

- Removed: zero-width characters (U+200B-U+200D), word joiner and invisible operators (U+2060-U+2064), U+180E, soft hyphen (U+00AD), and U+FEFF anywhere except a byte-order mark at the start, which stays.
- Removed: bidi controls U+202A-U+202E and U+2066-U+2069. Beyond watermarking, these are how Trojan Source attacks hide code.
- Replaced with a plain space: no-break space (U+00A0) and narrow no-break space (U+202F).
- Removed as whole lines: `Co-Authored-By:` trailers naming Claude, Codex, ChatGPT or an AI, `Generated with` lines naming them, the robot-emoji `Generated` line, and lines that start with `ai-assisted` or `ai-generated`.

## Humanizing

Only whole-line comments, in `.py .js .mjs .ts .tsx .jsx .sh .bash .css .go .rs .java .c .cpp .cc .cs .rb .yaml .yml .toml`. Python comments come from the tokenizer, so a `#` line inside a string literal is left alone and a file that does not tokenize is skipped; other languages use the line's leading comment marker, so a line inside a multi-line string or template literal that starts with `//` or `#` is the one case it can misread. Code, trailing comments and prose files (`.md`, `.txt`) are left as written.

- Em dash, en dash and horizontal bar become `-`; curly quotes become ASCII quotes; `…` becomes `...`; emoji are removed.
- A comment line is deleted when it is a conversational or placeholder line: `Here's the updated`, `Here is the updated`, `I hope this helps`, `Let me know if`, `Feel free to`, `As an AI`, `As an assistant`, `Add more as needed`, `Rest of the code`, `... existing code ...`, `... your code ...`, `Your code here`, or a comment that is only `Certainly`. The match is case-insensitive and anchored at the start of the comment. The list is `LLM_BOILERPLATE` in `harness/humanize.py`.

## Run it by hand

```sh
harness humanize --check path/   # list what would change; exits 1 if anything would
harness humanize path/           # apply
```

Directories are walked without entering `.git`, `node_modules`, virtualenvs, `dist`, `build` or hidden folders.

## Turn it off

Remove the `codex-harness watermark` entries from `~/.claude/settings.json` and `~/.codex/hooks.json`. The next `harness install` adds them back.
