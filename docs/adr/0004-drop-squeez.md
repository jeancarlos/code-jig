# 0004: Drop squeez

Status: accepted (2026-10-14)

## Decision
The harness does not include squeez, the tool-output compressor. It was also removed from the personal setup.

## Reason to exist
It was a candidate component for reducing input tokens. The data below says it does not.

## Data
Measured on the personal bench machine over 7 days:
- Savings were 0.05% of 1,857.8M input tokens.
- 67% of 40,105 Bash calls came out unchanged. 1,795 calls grew.
- The top 1% of calls gave 86% of the savings. The top 5% gave 96%.
- Issues #269 (concurrent init truncates `AGENTS.md`) and #270 were open on 2026-10-14.
- During the design session it swallowed command output entirely (17 tokens became 0).

## Cost
None. Codex already caps giant outputs with `tool_output_token_limit`.

## Kind
Script (rejected).

## Rejected alternatives
- Keep squeez as optional. A data-loss bug on `AGENTS.md` is too high a price for 0.05%.
- Build an equivalent. The only effect is a cap on giant outputs, which Codex already provides.
