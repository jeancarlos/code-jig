# Roadmap

What code-jig intends to do, and not do, over the next twelve months. It is a direction, not a promise; the maintainer is one person.

## Intends to do

- Keep up with Codex CLI releases: tiers, the `doctor` key scan and the exec-policy checks are tested against the real binary in CI (`codex-keys`), and a Codex change that breaks them is fixed in the next patch release.
- Work down the deferred review findings tracked as issues: [install](https://github.com/jeancarlos/code-jig/issues/1), [collector](https://github.com/jeancarlos/code-jig/issues/2), [cross-review](https://github.com/jeancarlos/code-jig/issues/3), [doctor](https://github.com/jeancarlos/code-jig/issues/4), [analyze and trace](https://github.com/jeancarlos/code-jig/issues/5) and [evidence](https://github.com/jeancarlos/code-jig/issues/6).
- Keep the supply chain as it is: every release is built once from the tag, signed with Sigstore, attested with SLSA provenance and published to PyPI from that same wheel.
- Keep the quality gates: tests with every change, statement coverage at 90 percent and branch coverage at 80 percent, CodeQL, gitleaks, osv-scanner, zizmor, REUSE and fuzzing.
- Test each new Python release as it ships and keep Python 3.11 and newer supported.
- Add and prove new skills on Codex through `code-jig skill-check --review --live` when a repeated job deserves one.
- Keep the documentation current: the runbooks, the architecture and security documents, and an ADR for each design choice.

## Does not intend to do

- Sit between the user and the model: no proxy, no daemon, no fork of Codex, no extra binaries.
- Add runtime dependencies: the core stays on the Python standard library.
- Send usage data anywhere: the token tracker and the evidence report stay local, and no telemetry is added.
- Translate the command-line output: messages stay in English.
- Support Python older than 3.11.
- Ship a graphical interface or a hosted service.
