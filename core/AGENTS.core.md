# codex-harness core rules

- One thread per task. When the topic changes, finish and start a new thread instead of continuing.
- Deterministic first. Before reasoning about anything countable or checkable, run the `harness` command or script that answers it.
- No polling loops. Do not chain `sleep`/`wait` calls when one blocking command or a single check gives the answer.
- Minimal code. Reuse what exists, prefer the standard library, delete before adding, no speculative abstractions.
- Root cause over symptom. Fix the shared function, not each caller.
