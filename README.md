# code-jig

**Make the official Codex CLI cheaper, safer and smarter, by configuration alone.**

code-jig is an open-source config pack for [OpenAI Codex](https://github.com/openai/codex). One command turns a stock install into a tuned setup: model tiers, automatic command review, a local token tracker, a set of battle-tested skills and a knowledge base that grows with you. No proxy, no daemon, no fork, no extra binaries. Just Python's standard library and the settings Codex already ships.

## Why I built it

I use coding agents every day, and I kept running into the same four problems.

**1. Tokens disappear and nobody can say where.** Input, not output, is the bill: every request re-sends the whole conversation. I wanted to see exactly where it goes (which sessions, which commands, how much the safety reviews cost) without sending a byte to anyone. So code-jig reads Codex's own session files into a local SQLite database after every turn. Its totals match Codex's own per-thread count and [ccusage](https://github.com/ryoppippi/ccusage) to the token.

**2. Safety that asks you a hundred times a day gets switched off.** Codex ships Guardian, a reviewer model that approves or denies commands leaving the sandbox. code-jig turns it on in every tier and lets you *add* local policy on top of the upstream rules instead of replacing them. You stay protected, and you stop clicking "approve".

**3. Tips are cheap, measurements are not.** Every choice here was tested on a real bench before it shipped, and some popular ideas did not survive. An output-compression layer I used to swear by turned out to save little; Codex's own `tool_output_token_limit` already covered what mattered, so it went. One Guardian review costs about 7,000 input tokens on the bench, 84% of them cached, so I know what safety costs instead of guessing.

**4. A setup should get better with use, and travel.** Lessons learned on a laptop usually die in that laptop's shell history. Here they become rules, Guardian policy, skills or knowledge facts in a small **overlay**, reviewed like code. The shared **core** stays clean and versioned; every machine gets its own overlay; nothing private ever flows back into the core.

## What you get

- **Tiers**: `default`, `deep`, `bulk`, `review`, each a generated Codex profile with its own model and reasoning effort. Pick the right brain for the job; [daily use](docs/runbooks/daily-use.md#which-model-for-which-job) maps jobs and skills to models for a public and an enterprise catalog.
- **Cheap subagents**: an `explorer` role on the `bulk` model answers lookups with line ranges instead of file dumps, a `reviewer` role on the `review` model attacks plans and findings, and a `judge` role on the `deep` model decides disputes. Code-writing subagents keep the session's model.
- **Guardian everywhere**, with your additions layered on the upstream policy.
- **Token tracker**: `code-jig tokens` shows input, cache hit, Guardian share, escalated commands, the heaviest sessions and per-model usage. All local.
- **Evidence**: `code-jig evidence` compares commits made in Codex sessions with the same repos' other commits (rework, `analyze` findings) and reports test runs, skill use, Guardian decisions and cost. Local data only.
- **Cross-family review**: `code-jig cross-review` sends your diff to a model from another family, read-only, before you push.
- **Sonar-style analysis without a server**: `code-jig analyze` runs the analyzers you already have (lizard, ruff, vulture, mypy, eslint with sonarjs, knip, tsc, dotnet build with SonarAnalyzer and NuGet audit, semgrep, gitleaks, osv-scanner) and groups the findings like Sonar: security, secrets, dependencies, bugs, types, unused code, complexity, duplication.
- **Requirement tracing**: `code-jig trace` checks which requirement IDs (from Azure DevOps, GitHub issues or a Markdown design) have tests, and which tests cite IDs that no longer exist.
- **Skills**: `cross-review`, `grilling` (stress-test a decision), `web-consensus` (settle facts against live sources), `improve` (turn a lesson into a durable change), and the deterministic toolbox: `code-analysis`, `regression-tests`, `hld-trace`, `bug-hunt` (property tests, fuzzing, mutation testing), `codegen` (OpenAPI clients, codemods) and `skill-validate`. Plus [superpowers](https://github.com/obra/superpowers) in one command.
- **Knowledge base**: one fact per file, indexed, pointed at by the generated AGENTS.md.
- **Sourced research**: `web-consensus` runs researchers, challenger and judge on the model each job needs, and `code-jig check-sources` confirms every quoted sentence is really on the cited page.
- **No AI attribution, no unreviewed prose**: an opt-in git gate strips AI co-author lines from commit messages, removes invisible characters from staged files, refuses agent-written docs until you commit them yourself, and refuses pushes that still carry attribution.
- **Skills proven on Codex**: `code-jig lint-skill` and the `skill-validate` skill check a skill's text; `code-jig skill-check --review --live` has Codex review it and run its test cases, and CI refuses a skill whose stamp is not current.
- **Edit feedback**: after every agent write, syntax errors and undefined names in Python, JSON and TOML, and a notice when a test is deleted or skipped, go straight back to the model. Nothing blocks.
- **Doctor**: checks the binary, the pins, every tier's model against your account's catalog, the subagent roles, managed requirements, the AGENTS.md budget and the size of the skills list sent with every request, and probes each tier for free.
- **Works on locked-down machines**: native Windows support, no scripts required, respects administrator-managed Codex config and tells you how it differs from what was tested.

## Quick start

Requires Python 3.11+ and git. Your overlay is a folder or git repository with an `overlay.toml`; see [personalizing](docs/personalizing.md). With no overlay, the installer makes `~/code-jig-overlay` for you.

### From a release (no git checkout)

Linux and macOS:

```sh
curl -fsSL https://code-jig.jeansouza.dev/setup | python3 -I - --overlay <path|git-url>
```

Windows (PowerShell):

```powershell
irm https://code-jig.jeansouza.dev/setup | py -3 -I - --overlay <path|git-url>
```

A piped script cannot check itself. To read what you run, download only `bootstrap.py`, read it, then run it:

```sh
curl -fsSL -o bootstrap.py https://code-jig.jeansouza.dev/setup
python3 -I bootstrap.py --overlay <path|git-url>
```

On Windows: `py -3 -I bootstrap.py --overlay <path|git-url>`. The same file is at `https://github.com/jeancarlos/code-jig/releases/latest/download/bootstrap.py`.

`bootstrap.py` has no checksum of its own; reading it is the check. The bootstrap downloads the zip itself and checks it against the release's `SHA256SUMS`. That catches a corrupted download, but not a compromised GitHub release.

The GitHub URL above works when `code-jig.jeansouza.dev` is down. The bootstrap also falls back to GitHub on its own. Releases before v0.11.0 have no zip.

The bootstrap unpacks the release into `~/.local/share/code-jig/vX.Y.Z/` (`%LOCALAPPDATA%\code-jig\vX.Y.Z\` on Windows), runs `install`, writes `code-jig` and `cjig` launchers in `~/.local/bin` and runs `doctor`. The overlay's `core_version` picks the release. To change it, edit `core_version` and run the bootstrap again; see [upgrade and rollback](docs/runbooks/upgrade-and-rollback.md).

### From a checkout (to change the core)

```sh
git clone https://github.com/jeancarlos/code-jig
cp -r code-jig/overlay-examples/personal ~/code-jig-overlay   # your overlay
export CODE_JIG_OVERLAY=~/code-jig-overlay
cd code-jig
./install.sh                                  # Windows: py -3 -m codejig install
PYTHONPATH=. python3 -m codejig doctor
codex --profile default
```

Edit `~/code-jig-overlay/profiles.toml` to pick your models; `doctor` lists the ones your account can use.

### What the install counts

The tool sends nothing. The download site counts requests for `bootstrap.py` and for release zips, and stores the event, the version, the client type (curl, PowerShell, Python or other) and the country. It does not store your IP address, your user-agent string or any install ID. The counts are request counts, not installs. See [ADR 0027](docs/adr/0027-install-from-a-release-url.md).

## Documentation

| Read | When |
|---|---|
| [Daily use](docs/runbooks/daily-use.md) | Tiers, skills, reviews, the repo's own AGENTS.md |
| [Doctor](docs/runbooks/doctor.md) | What every check means and how to fix it |
| [Tokens](docs/runbooks/tokens.md) | Reading the usage report |
| [Evidence](docs/runbooks/evidence.md) | Whether code-jig pays off: rework, tests, skills, cost |
| [Code quality](docs/runbooks/code-quality.md) | `analyze`, `trace`, the toolbox skills, installing the tools |
| [Managed machines](docs/runbooks/managed-machine.md) | Installing where someone else administers the machine |
| [Network and certificates](docs/runbooks/network-and-certificates.md) | TLS-inspecting networks, git and CLI tools in the sandbox |
| [Circuit breaker](docs/runbooks/circuit-breaker.md) | When Guardian stops a turn |
| [Commit attribution](docs/runbooks/commit-attribution.md) | Codex's co-author trailer and how to turn it off |
| [Watermarks, humanizing and edit feedback](docs/runbooks/watermark-and-humanize.md) | What the write hook strips from agent output, what it reports back to the model, and how to run or disable it |
| [Upgrade and rollback](docs/runbooks/upgrade-and-rollback.md) | Updates, rollbacks, uninstalling |
| [Personalizing](docs/personalizing.md) | Overlay slots, pinning, the clean-room rule |
| [Decisions](docs/adr/) | Why each design choice was made, and what was rejected |
| [Contributing](CONTRIBUTING.md) | Code rules and tests |
| [Editing the deck](docs/deck/README.md) | The presentation and its data files |

## Principles

- **Configuration, not interception.** code-jig writes files Codex reads. It never sits between you and the model.
- **Measure, then decide.** Bench data in the repo, never guesses.
- **Additive safety.** Local policy extends upstream policy; it never replaces it.
- **Clean-room overlays.** Private context stays in private overlays. The core carries only what anyone could use.

## License

Apache-2.0.
