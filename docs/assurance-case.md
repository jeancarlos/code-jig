# Assurance case

The claim: code-jig meets the security requirements in [security.md](security.md) well enough for a tool that configures a coding agent and runs on a developer's own machine. The argument has four parts: the threat model, the trust boundaries, the secure design principles applied, and the common weaknesses countered. Each point names the code or the check that backs it.

## Threat model

Assets: the files in the user's home that Codex reads (instructions, rules, policy), the user's source tree, the API key used by `humanize --rewrite`, the usage database, and the integrity of the installed package.

Attackers considered:

- A malicious repository or file the agent works on, aiming to make a hook write outside the tree, run a command or crash the tooling.
- A malicious web page or redirect aimed at `check-sources`, trying to reach a private network address.
- A malicious or compromised gateway or model reply aimed at `humanize --rewrite`, trying to insert content or capture the key.
- A tampered package or release asset between the maintainer and the user.
- A local user racing the installer with a symlink or hard link swap.

Out of scope: an attacker who already controls the user's account, overlay or machine, and flaws in Codex, Python or GitHub themselves.

## Trust boundaries

1. Agent and repository content to code-jig: hook JSON on stdin, session files, files under analysis, analyzer output. Untrusted.
2. code-jig to the filesystem: the Codex home, skills directory, Claude Code settings and working tree. Writes cross this boundary.
3. code-jig to the network: `check-sources` and `humanize --rewrite` only.
4. The project to the user: the signed, attested wheel from PyPI and GitHub releases.

## Secure design principles

- Least privilege: no daemon, no elevated rights, no network by default, no runtime dependencies (`pyproject.toml` has `dependencies = []`). The release workflows declare `contents: read` and grant more only to the job that needs it.
- Fail-safe defaults: a file code-jig did not generate is backed up, not overwritten (`install.write_generated`); an unknown or malformed record is skipped; `core_writable = false` makes `doctor` fail on any edit of the installed core.
- Complete mediation of paths: `atomicwrite.resolve_inside` returns only a regular file that resolves inside the root, and reads and writes re-check it against swaps, symlinks, junctions and hard links (tests in `tests/test_atomicwrite.py`).
- Economy of mechanism: standard library only, small modules, one parser per input kind.
- Open design: every design choice has a decision record in [adr](adr), and the code is public under Apache-2.0.
- Separation of duties in release: CI builds once; signing and provenance use short-lived OIDC identities, so no private signing key is stored anywhere; the PyPI upload needs a manual environment approval and re-verifies the attestation and checksum first.
- Defense in depth: hooks fail open for availability while the git gate and doctor fail closed for integrity.

## Common weaknesses countered

| Weakness | Counter |
|---|---|
| Shell and command injection | Every subprocess call passes a list, never user text in a shell. The one `shell=True` runs the test command the user configured themselves (`gitgate.py`). Checked by CodeQL. |
| Path traversal and symlink attacks | `resolve_inside` allowlists regular files inside a root; archive members are staged from `git archive` by the build, not extracted from user input. |
| Server-side request forgery | `sources.py` refuses non-public addresses before connecting, checks the connected peer address, and checks every redirect (`tests/test_sources.py`). |
| Credential leakage | The key is read from the environment or a user file, sent only over https or to loopback, and never across a redirect (`rewrite.gateway`). gitleaks scans the full history in CI. |
| Improper certificate validation | The Python default context is used; nothing sets `CERT_NONE` or `check_hostname = False`. |
| Untrusted deserialization | Only `json`, `tomllib` and `sqlite3` parse input; there is no `pickle`, `eval` or `exec`. |
| Malformed input crashing tools | Parsers return errors or quarantine the record; ClusterFuzzLite fuzzes the parsers on every code change and before each release (`fuzz/targets.py`). |
| Weak cryptography | The only cryptography is `hashlib` SHA-256 for digests. No custom primitives, no passwords stored. |
| Vulnerable dependencies and tools | No runtime dependencies; CI tools are hash-locked, GitHub Actions are pinned by commit, osv-scanner and Dependabot watch them. |
| Tampered releases | Sigstore signatures, SLSA provenance, `SHA256SUMS`, and the `doctor` package digest; verification steps are in the [README](../README.md#verify-a-release). |
| Workflow injection | zizmor lints the workflows; untrusted values go through `env:`, never inline in `run:`. |

## Evidence in CI

Each push runs the unit tests on Linux and Windows, CodeQL for Python, JavaScript and Actions, ruff, gitleaks over the full history, osv-scanner, zizmor, REUSE, the coverage gates (statements 90 percent, branches 80 percent) and the wheel build. Fuzzing runs on code changes and before every release. See [.github/workflows](../.github/workflows).

## Known gaps

- There is one maintainer, so no second human reviews a change before it ships and no independent security review has been done.
- The cross-review reviewer's read-only shell can be steered by injected text; it is documented and has no write access.
