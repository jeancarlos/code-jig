---
name: web-consensus
description: Use when a question has to be settled against the live web rather than from memory - researching a topic, proving or disproving a claim, checking whether something is still true, a sourced second opinion on a factual question - or when the user says "research", "prove it", "with sources", "check if this is true", "still accurate?".
---

# Web consensus

Researchers gather evidence, a blind challenger attacks it, the disputed points are researched again from scratch, every cited link is checked, and the verdict cites sources only.

Use one subagent per role when subagents are available: researchers (steps 1 and 3) as `explorer`, which runs on the cheap bulk tier, and the challenger as `reviewer`, which runs on a different model family. Each subagent gets its own brief and nothing about the others, so no role can quietly agree with another. Without subagents, do the roles one after another and keep each role's notes in its own file.

## Flow

1. **Evidence.** One researcher per angle, run in parallel. Each returns claim / URL / exact quote triples and nothing else.
   - `direct`: the question as asked.
   - `disconfirming`: the strongest evidence that the expected answer is wrong, such as corrections, retractions, errata and dissenting primary sources.
   - `primary-source`: official docs, specifications, source code, changelogs and papers only. No blogs or aggregators.
   - `academic`, when the question has a research literature: papers, reproductions and negative results.

   Vary the wording of the searches between angles. The same index returns very different results for differently worded questions.

2. **Challenge.** A challenger that cannot search reads every evidence file. It rules on every claim with one line each, `OK`, `DOUBT` or `MISMATCH` (the quote does not support the claim), then lists the questions that would settle each dispute.

3. **Cold verification.** For each of those questions, a fresh researcher gets only the question: no evidence and no challenge. A check that can see what it is checking re-derives the original reasoning instead of testing it.

4. **Link check.** Request every cited URL (`curl -sIL -o /dev/null -w "%{http_code}" URL`, or the platform equivalent). A claim can only be agreed if it stands behind a URL that answered 200. A 403 is usually bot-blocking, not absence: say so.

5. **Verdict.** Answer the question in a short paragraph. Then list agreed claims, disputed claims and claims nobody could source, each with its URL and quote. Then give your confidence and what new evidence would change the answer. No claim may appear without a URL and a quote.

## Rules

- The searcher never dictates the answer alone. One evidence set is one retrieval's opinion; say how many independent sets agree.
- Prefer primary sources over secondary ones, and recent over old when the subject moves.
- When results look stale, rerun the researchers with live search: `codex -c web_search="live" ...`.
- Do not answer from memory. If the web is silent, say that.
