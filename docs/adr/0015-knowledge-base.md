# 0015: An overlay knowledge base with a capped index

Status: accepted (2026-10-14)

## Decision
An overlay may keep `knowledge/`, one Markdown file per fact plus `knowledge/INDEX.md` with one line per file. When the index exists, `install` appends a short section to the generated `AGENTS.md` that points to it by absolute path. Doctor warns when the index is over 150 lines, or when `knowledge/` has no index. The `improve` skill curates it. Codex's native memory stays on for automatic recall.

## Reason to exist
Native memory is opaque and stays on one machine. Files can be reviewed, versioned with the overlay and moved to a new laptop.

## Data
- The memory index this design came from grew to 333 lines and 42 KB and is now truncated when it loads, so the cap is the point.
- The pointer costs a few dozen bytes of the `AGENTS.md` chain, which doctor measures against `project_doc_max_bytes` (0006).

## Cost
Five lines in `render_agents` and one doctor check.

## Kind
Model writes, script checks the cap.

## Rejected alternatives
- Inlining the facts into `AGENTS.md`: it would grow past the chain cap, and Codex silently stops adding files there.
- Native memory only: not reviewable or portable, and it cannot separate corporate from personal knowledge.
