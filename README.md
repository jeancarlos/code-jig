# codex-harness

**Make the official Codex CLI cheaper, safer and smarter, by configuration alone.**

codex-harness is an open-source config pack for [OpenAI Codex](https://github.com/openai/codex). One command turns a stock install into a tuned setup: model tiers, automatic command review, a local token tracker, a set of battle-tested skills and a knowledge base that grows with you. No proxy, no daemon, no fork, no extra binaries. Just Python's standard library and the settings Codex already ships.

## Why I built it

I use coding agents every day, and I kept running into the same four problems.

**1. Tokens disappear and nobody can say where.** Input, not output, is the bill: every request re-sends the whole conversation. I wanted to see exactly where it goes (which sessions, which commands, how much the safety reviews cost) without sending a byte to anyone. So the harness reads Codex's own session files into a local SQLite database after every turn. Its totals match Codex's own per-thread count and [ccusage](https://github.com/ryoppippi/ccusage) to the token.

**2. Safety that asks you a hundred times a day gets switched off.** Codex ships Guardian, a reviewer model that approves or denies commands leaving the sandbox. The harness turns it on in every tier and lets you *add* local policy on top of the upstream rules instead of replacing them. You stay protected, and you stop clicking "approve".

**3. Tips are cheap, measurements are not.** Every choice here was tested on a real bench before it shipped, and some popular ideas did not survive. An output-compression layer I used to swear by turned out to save little; Codex's own `tool_output_token_limit` already covered what mattered, so it went. One Guardian review costs about 7,000 input tokens on the bench, 84% of them cached, so I know what safety costs instead of guessing.

**4. A setup should get better with use, and travel.** Lessons learned on a laptop usually die in that laptop's shell history. Here they become rules, Guardian policy, skills or knowledge facts in a small **overlay**, reviewed like code. The shared **core** stays clean and versioned; every machine gets its own overlay; nothing private ever flows back into the core.

## What you get

- **Tiers**: `default`, `deep`, `bulk`, `review`, each a generated Codex profile with its own model and reasoning effort. Pick the right brain for the job.
- **Guardian everywhere**, with your additions layered on the upstream policy.
- **Token tracker**: `harness tokens` shows input, cache hit, Guardian share, escalated commands, the heaviest sessions and per-model usage. All local.
- **Cross-family review**: `harness cross-review` sends your diff to a model from another family, read-only, before you push.
- **Skills**: `cross-review`, `grilling` (stress-test a decision), `web-consensus` (settle facts against live sources), `improve` (turn a lesson into a durable change). Plus [superpowers](https://github.com/obra/superpowers) in one command.
- **Knowledge base**: one fact per file, indexed, pointed at by the generated AGENTS.md.
- **Doctor**: checks the binary, the pins, every tier's model against your account's catalog, managed requirements and the AGENTS.md budget, and probes each tier for free.
- **Works on locked-down machines**: native Windows support, no scripts required, respects administrator-managed Codex config and tells you how it differs from what was tested.

## Quick start

Requires Python 3.11+ and Codex.

```sh
git clone https://github.com/jeancarlos/codex-harness
cp -r codex-harness/overlay-examples/personal ~/codex-overlay   # your overlay
export CODEX_HARNESS_OVERLAY=~/codex-overlay
cd codex-harness
./install.sh                                  # Windows: py -3 -m harness install
PYTHONPATH=. python3 -m harness doctor
codex --profile default
```

Edit `~/codex-overlay/profiles.toml` to pick your models; `doctor` lists the ones your account can use.

## Documentation

| Read | When |
|---|---|
| [Daily use](docs/runbooks/daily-use.md) | Tiers, skills, reviews, the repo's own AGENTS.md |
| [Doctor](docs/runbooks/doctor.md) | What every check means and how to fix it |
| [Tokens](docs/runbooks/tokens.md) | Reading the usage report |
| [Managed machines](docs/runbooks/managed-machine.md) | Installing where someone else administers the machine |
| [Network and certificates](docs/runbooks/network-and-certificates.md) | TLS-inspecting networks, git and CLI tools in the sandbox |
| [Circuit breaker](docs/runbooks/circuit-breaker.md) | When Guardian stops a turn |
| [Commit attribution](docs/runbooks/commit-attribution.md) | Codex's co-author trailer and how to turn it off |
| [Upgrade and rollback](docs/runbooks/upgrade-and-rollback.md) | Updates, rollbacks, uninstalling |
| [Personalizing](docs/personalizing.md) | Overlay slots, pinning, the clean-room rule |
| [Decisions](docs/adr/) | Why each design choice was made, and what was rejected |
| [Contributing](CONTRIBUTING.md) | Code rules and tests |
| [Editing the deck](docs/deck/README.md) | The presentation and its data files |

## Principles

- **Configuration, not interception.** The harness writes files Codex reads. It never sits between you and the model.
- **Measure, then decide.** Bench data in the repo, never guesses.
- **Additive safety.** Local policy extends upstream policy; it never replaces it.
- **Clean-room overlays.** Private context stays in private overlays. The core carries only what anyone could use.

## License

Apache-2.0.
