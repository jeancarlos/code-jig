# Governance

code-jig is a small open-source project run by one maintainer under the benevolent-dictator model: the maintainer makes every final decision, in public, and writes the reason down.

## Roles and responsibilities

| Role | Who | Responsibilities |
|---|---|---|
| Maintainer and owner | Jean Souza ([@jeancarlos](https://github.com/jeancarlos)), listed in [.github/CODEOWNERS](.github/CODEOWNERS) | Decides what is in scope. Reviews and merges every pull request into `develop`. Opens, merges and tags the promote from `develop` to `main`. Approves the `pypi` environment that publishes a release. Triages issues. Handles private vulnerability reports within the times in [SECURITY.md](SECURITY.md). Enforces the [code of conduct](CODE_OF_CONDUCT.md). Keeps the OpenSSF Best Practices answers in [docs/best-practices.md](docs/best-practices.md) true. |
| Contributor | Anyone who opens an issue or a pull request | Follows [CONTRIBUTING.md](CONTRIBUTING.md): a test with every change, a `Signed-off-by` line on every commit, no new dependencies. Gets a written reason when a change is declined. |
| Reporter | Anyone who reports a bug or a vulnerability | Uses issues for bugs and the private advisory form for vulnerabilities. Is credited in the release notes when a vulnerability is fixed, unless they ask not to be. |

## How decisions are made

- Small changes: a pull request into `develop`, reviewed by the maintainer, merged when CI passes. The review checks the points in [CONTRIBUTING.md](CONTRIBUTING.md#code-review).
- Design decisions that are hard to reverse get a short record in [docs/adr](docs/adr) with the options that were rejected.
- Scope questions (a new dependency, a daemon, a proxy) are answered by the principles in the [README](README.md#principles): configuration, not interception; no runtime dependencies.
- Disputes: discuss in the issue or pull request. If there is no agreement, the maintainer decides and records the reason there. The decision can be reopened with new evidence.
- A contributor who sends sustained, high-quality work can be invited to become a co-maintainer: write access, review rights and a place in `CODEOWNERS`. The maintainer decides, and says so in an issue.

## Continuity

Today the project has one maintainer, so it does not meet the OpenSSF requirement to continue within a week if that person is lost, and its bus factor is 1. The mitigations are real but partial: the code, the history and the signed releases are public, the Apache-2.0 license allows anyone to fork and continue, and the release pipeline is fully scripted in [.github/workflows/release.yml](.github/workflows/release.yml). What is missing is a second person holding admin access to the GitHub repository, the `pypi` environment and the PyPI project. Adding a co-maintainer is the fix, and it depends on someone contributing regularly and being invited.
