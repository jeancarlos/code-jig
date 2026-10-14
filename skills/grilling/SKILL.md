---
name: grilling
description: Use when the user wants a plan, decision, design or idea stress-tested before committing to it, or says "grill me", "grill this", "stress-test this", "poke holes in this", "what am I missing". Do not fire on your own.
---

# Grilling

Interview the user until you both understand the decision the same way. Map it as a design tree: every decision branches into the decisions that hang off it.

Work the tree in rounds. The frontier is every decision whose prerequisites are already settled, which are the questions you can ask now without guessing answers you have not heard. Ask the frontier at most three questions per round. Number each question, give the options, and give your recommendation. Then wait for the answers before the next round.

Nothing stays in the user's head between turns, so every round carries its own state.

## Round format

```
**Settled (N):** <one short clause per settled decision, most recent last>

**Round K. Frontier: <count>.**

**Q1 - <title>**: <question>

a) ... b) ... c) ...

Recommendation: <your answer, what you would reject and why, and context they may have forgotten>

**Deferred**: <titles of questions blocked on this round, or "none">
```

Never skip the settled line or the deferred line, even in a one-question round. A question whose answer depends on another open question belongs to a later round. A frontier wider than three spills into the next round, and its titles go in the deferred list.

## Skip

The user may answer `skip`. Take your recommendation, mark it `(assumed)`, and keep going. At the end, list every assumed answer once for a yes or no confirmation.

## Facts are yours, decisions are theirs

When a question needs a fact from the environment (files, tools, docs, the web), find it yourself, with a subagent when one is available. Never ask the user for something you can look up. Only questions that depend on a pending lookup wait for it; ask the rest of the frontier now. State the fact when you use it.

## Tree file

Write `grill-<slug>.md` in a scratch directory and update it at the end of every round:

```markdown
# Grill: <topic>

## Settled
- Q1 <title>: <answer> (over <rejected option>) - <one-line why>
- Q2 <title>: <answer> (assumed)

## Open
- Frontier: <titles>
- Deferred: <titles>
```

## Ending

The session ends when the frontier is empty: every branch visited, nothing silently assumed. Confirm the assumed answers, then summarise the settled tree and ask whether to write it up as a spec or plan. Do not act on the outcome until the user confirms you agree.

These thoughts mean you are quitting early. Recompute the frontier and ask the next round instead: "the rest is implementation detail", "we can figure that out later", "the remaining questions are obvious", "good enough to start".
