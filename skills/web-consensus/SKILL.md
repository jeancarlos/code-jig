---
name: web-consensus
description: Use when a question has to be settled against the live web rather than from memory - researching a topic, proving or disproving a claim, checking whether something is still true, a sourced second opinion on a factual question - or when the user says "research", "prove it", "with sources", "check if this is true", "still accurate?".
---

# Web consensus

Cheap researchers gather evidence in parallel, a reviewer from another model family attacks it, the disputed points are researched again from scratch, a script checks every link and quote, and a judge on the strongest model writes the verdict from sources only.

## Who does what

| Step | Subagent role | Runs on |
|---|---|---|
| Evidence, cold verification | `explorer`, one per angle or question, in parallel | `bulk` tier: fast and cheap |
| Challenge | `reviewer` | `review` tier: another model family |
| Link and quote check | `harness check-sources` | no model |
| Verdict | `judge` | `deep` tier: the strongest model |

This skill asks for subagents: every role in the table runs through `spawn_agent` with that `agent_type`, even when you wait for its result before the next step, because the point is a different model and a fresh context, not speed. Each subagent gets its own brief and nothing about the others, so no role can quietly agree with another, and never a fork of this conversation. You only route: write the evidence files, run the script, pass material between roles. Run the whole flow even when the answer looks obvious or one page settles it: "it's a simple fact", "the docs already say it" and "one search is enough" are the answers from memory this skill replaces. If `spawn_agent` is not available in this session, stop and say so: a consensus from one model playing every role is not this skill's output, so do not play the roles yourself.

## Flow

1. **Evidence.** One `explorer` per angle. Each returns claim / URL / exact quote triples and nothing else. Write them to `evidence-<angle>.jsonl` in the workspace, one JSON object per line: `{"claim": "...", "url": "...", "quote": "..."}`.
   - `direct`: the question as asked.
   - `disconfirming`: the strongest evidence that the expected answer is wrong: corrections, retractions, errata, dissenting primary sources.
   - `primary-source`: official docs, specifications, source code, changelogs and papers only.
   - `academic`, when the question has a research literature: papers, reproductions, negative results.

   Vary the wording of the searches between angles. The same index returns very different results for differently worded questions.

2. **Check.** `harness check-sources "evidence-*.jsonl"` (the command expands the pattern itself, so the same line works in PowerShell). It fetches each URL once and reports per claim: `ok` (the page contains the quote), `quote-missing`, `dead`, `blocked` (401/403/429: usually bot-blocking, not absence), `unreadable` (PDF or binary: quote unverified). It needs the network, so in a sandbox it must run with escalation; one run covers every file.

3. **Challenge.** A `reviewer` reads the evidence files and the check report, and is told not to search. It rules on every claim with one line each, `OK`, `DOUBT` or `MISMATCH`, then lists the questions that would settle each dispute.

4. **Cold verification.** For each of those questions, a fresh `explorer` gets only the question: no evidence and no challenge. Write its triples to `evidence-cold.jsonl` and run the check on it. When the challenge lists no disputes, skip this step and say so in the report; there is then only the first check report.

5. **Verdict.** A `judge` gets the question, every evidence file, every check report (one, or two after cold verification) and the challenge. It answers in a short paragraph, then lists agreed, disputed and unsourced claims with URL and quote, its confidence, and what new evidence would change the answer. Relay the verdict; do not rewrite it.

## Rules

- A claim can only be agreed when `check-sources` says `ok`, or `unreadable` with the quote confirmed by a second source.
- The searcher never dictates the answer alone. Say how many independent evidence sets agree.
- Prefer primary sources over secondary ones, and recent over old when the subject moves.
- When results look stale, ask the user to start the session with live search (`codex -c web_search="live"`).
- If web search is not available in this session, say so and stop. Do not answer from memory.

## Common mistakes

| Mistake | Instead |
|---|---|
| Answering from one search because the question looks easy | Run every step; the user asked for sources checked by roles that did not write them. |
| Forking this conversation into a researcher | A fresh brief; a fork re-reads everything and inherits your bias. |
| Judging in the main session | The `judge` role exists so the verdict runs on the strongest model whatever tier this session uses. |
| Treating `blocked` as `dead` | Say it was blocked; find a second source or quote it as unverified. |
| Paraphrasing in the `quote` field | The check needs the exact words on the page. |
