# code-jig core rules

- One thread per task. When the topic changes, finish and start a new thread instead of continuing.
- Deterministic first. Before reasoning about anything countable or checkable, run the `code-jig` command or script that answers it.
- No polling loops. Do not chain `sleep`/`wait` calls when one blocking command or a single check gives the answer.
- Minimal code. Reuse what exists, prefer the standard library, delete before adding, no speculative abstractions.
- Root cause over symptom. Fix the shared function, not each caller.
- No AI attribution. Never write `Co-authored-by` or `Generated with` lines for an AI, `AI-assisted` notes or robot emoji in commits, pull requests, comments or files. A commit already on a remote is locked: never rewrite it to remove attribution; tell the user.
- Subagent check. Before each `spawn_agent`, decide whether the job needs one and which `agent_type` fits. Skip it for one grep, one file read or a few commands: do those yourself. `explorer` (bulk tier) for lookups, `worker` for one bounded change with a clear file scope, checked before the next, `reviewer` (review tier) to attack a plan, diff or claim before acting on it, `judge` (deep tier) to decide between gathered conflicting claims, `default` for any other self-contained task. Keep architecture, subtle multi-file logic, security and root-cause debugging in the main thread, and say so when they need the deep tier. At most three in parallel unless asked. Name the agent you picked and why in one line.
