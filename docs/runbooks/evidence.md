# Runbook: is code-jig paying off?

`code-jig evidence` answers three questions with numbers: do commits made in Codex sessions need less rework than the rest of the same repos, which parts of code-jig actually fire, and what it all costs. It reads two things only: the tracker database the `Stop` hook fills (`~/.local/share/code-jig/usage.sqlite3`) and `git log` of the repos your sessions ran in. Nothing leaves the machine.

```sh
PYTHONPATH=<core> python3 -m codejig evidence                    # last 90 days, every repo Codex worked in
PYTHONPATH=<core> python3 -m codejig evidence --days 30          # a shorter window
PYTHONPATH=<core> python3 -m codejig evidence --repo ~/src/app   # one repo, even one Codex never ran in
PYTHONPATH=<core> python3 -m codejig evidence --analyze 10       # add analyze findings on 10 sampled commits per group (slow)
PYTHONPATH=<core> python3 -m codejig evidence --json > evidence.json
```

It runs `collect` first, so a session that ended in an error (which skips the `Stop` hook) is still counted. After upgrading from a version before v0.7.0, run `code-jig collect --rescan` once so older sessions get their exit codes, skill reads and Guardian outcomes too.

## How commits are split

Every Codex session has a window: from its first recorded moment to its last, including its subagents and Guardian reviews, plus two hours of grace for the commit that follows the work. The session's working directory is mapped to its git repo, so a session started in `src/api` counts for the whole repo.

| Group | A commit belongs here when |
|---|---|
| `harness` | Its author date falls inside a session window for that repo. |
| `baseline` | It is in the same repo and falls outside every window: older than the first session, or written without Codex since. |

The author date is used because it survives a rebase, an amend or a cherry-pick; those reset the committer date to the moment they ran.

## The report, line by line

| Line | Meaning | Look at it when |
|---|---|---|
| `harness` / `baseline` `rework` | Share of mature commits that were reverted, fixed up (`fixup!`, `squash!`) or had the same lines changed again within 14 days. | The harness group sits well above the baseline: the sessions ship code that comes back. |
| `insufficient (n=…)` | Fewer than 20 mature commits in the group, so no rate is printed. | Always: widen `--days` or wait. A rate from ten commits is noise. |
| `findings per 100 changed lines` | With `--analyze N`: `analyze` findings by category in the files each sampled commit touched, per 100 lines it added or changed. | Security or bug findings per 100 lines are higher in the harness group. |
| `Testing` | How many sessions ran a test command, and how many of those runs passed. Runs whose exit code never appeared (a cell still running) count for the session but not as a pass or fail. | Few sessions ran tests: ask for the `regression-tests` skill, or put it in the repo's AGENTS.md. |
| `Skills` and `never fired` | Sessions that read each skill, and installed skills no session read. | A skill that never fires is either not needed or described badly; see `docs/runbooks/daily-use.md`. |
| `Guardian` | Review outcomes (`allow`, `deny`), and how many commands asked for escalation. | Many denials: see `circuit-breaker.md`. |
| `Cost` | Tokens per session and per harness commit, cache hit, compactions, median session length. | Tokens per harness commit climb while rework does not fall. |
| `Sessions outside any git repo` | Working directories that no longer exist or are not in a repo. | Expected for scratch folders; a real project here means its folder moved. |

Mature means at least 14 days old: a younger commit has not had the time to be reworked, so counting it would flatter both groups.

## Limits

- This is correlation, not causation. Session work and baseline work are different tasks, and nobody picks which gets done with Codex at random. Read the numbers as a trend over months, not as proof.
- Only commits reachable from the repo's current checkout are read. Work on a branch that is not merged into it is invisible, and a forge squash merge replaces the session's commits with one commit dated at the merge.
- A session that commits several times and reworks its own lines counts that as rework, which works against the harness group.
- Same-line rework compares line numbers between commits. Other commits in between shift lines, so the match is approximate in both directions.
- The dashboard's test pass rate treats any command containing `pytest`, `unittest`, `dotnet test`, `npm test`, `pnpm test`, `yarn test`, `run test`, `vitest` or `jest` as a test run, the same rule as the report.
- `--analyze` checks out each sampled commit in a temporary worktree with git hooks disabled and runs every installed analyzer except the history scan. Findings count only when they sit on lines the commit added or changed. A commit whose checkout fails, where no analyzer runs, or where an analyzer errors is left out and reported as `could not be analyzed`. It takes as long as `analyze` does, times N, for each group in each repo.

## Using it on a managed machine

Run it once a week for a month and keep the JSON:

```sh
PYTHONPATH=<core> python3 -m codejig evidence --days 90 --json > evidence-$(date +%F).json
```

Compare the files month to month. The database, the repos and the report all stay on the machine.
