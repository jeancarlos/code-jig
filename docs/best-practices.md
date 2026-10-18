# OpenSSF Best Practices answers

Answers for <https://www.bestpractices.dev> (passing level). Project URL: <https://github.com/jeancarlos/code-jig>.

| Criterion | Answer | Evidence |
|---|---|---|
| description_good, interact, contribution, contribution_requirements | Met | https://github.com/jeancarlos/code-jig/blob/main/README.md, https://github.com/jeancarlos/code-jig/blob/main/CONTRIBUTING.md (How to contribute - https://github.com/jeancarlos/code-jig/blob/main/CONTRIBUTING.md#how-to-contribute, What makes a contribution acceptable - https://github.com/jeancarlos/code-jig/blob/main/CONTRIBUTING.md#what-makes-a-contribution-acceptable, Rules - https://github.com/jeancarlos/code-jig/blob/main/CONTRIBUTING.md#rules) |
| floss_license, floss_license_osi, license_location | Met | Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0), https://github.com/jeancarlos/code-jig/blob/main/LICENSE, https://github.com/jeancarlos/code-jig/blob/main/LICENSES/Apache-2.0.txt ; OSI approval: https://opensource.org/license/apache-2-0 |
| documentation_basics, documentation_interface | Met | https://github.com/jeancarlos/code-jig/blob/main/README.md, https://github.com/jeancarlos/code-jig/tree/main/docs |
| sites_https, delivery_mitm | Met | PyPI (https://pypi.org/project/code-jig/) and github.com (https://github.com/jeancarlos/code-jig) only, TLS; pip (https://pip.pypa.io/) checks the PyPI sha256, and the wheel is signed and attested |
| sites_password_security | N/A | the project's sites store no user passwords |
| discussion, english | Met | GitHub issues (https://github.com/jeancarlos/code-jig/issues) and pull requests (https://github.com/jeancarlos/code-jig/pulls), English |
| maintained | Met | commits every week (https://github.com/jeancarlos/code-jig/commits/main) |
| repo_public, repo_track, repo_interim, repo_distributed | Met | public git repository (https://github.com/jeancarlos/code-jig) on GitHub, with branches (https://github.com/jeancarlos/code-jig/branches) and full history |
| version_unique, version_semver, version_tags | Met | tags (https://github.com/jeancarlos/code-jig/tags) vX.Y.Z, and `VERSION` in https://github.com/jeancarlos/code-jig/blob/main/codejig/__init__.py |
| release_notes | Met | releases (https://github.com/jeancarlos/code-jig/releases): each release's notes are its section of https://github.com/jeancarlos/code-jig/blob/main/CHANGELOG.md (written for users, with the upgrade steps), published by https://github.com/jeancarlos/code-jig/blob/main/.github/workflows/release.yml through https://github.com/jeancarlos/code-jig/blob/main/.github/scripts/release_notes.py; the job fails without a section and never uses the git log |
| release_notes_vulns | N/A | no publicly known vulnerability fixed in a release so far |
| report_process, report_tracker, report_responses, enhancement_responses, report_archive | Met | GitHub issues (https://github.com/jeancarlos/code-jig/issues), https://github.com/jeancarlos/code-jig/blob/main/CONTRIBUTING.md |
| vulnerability_report_process, vulnerability_report_private, vulnerability_report_response | Met | https://github.com/jeancarlos/code-jig/blob/main/SECURITY.md, GitHub private vulnerability reporting (https://github.com/jeancarlos/code-jig/security/advisories/new), 7 day acknowledgement |
| build, build_common_tools, build_floss_tools | N/A | pure Python; the wheel is built from `git archive` of the tag by https://github.com/jeancarlos/code-jig/blob/main/.github/scripts/build_wheel.py with hash-locked build tools |
| test, test_invocation, test_most, test_continuous_integration | Met | `python -m unittest discover -s tests`, coverage floor 93 percent, https://github.com/jeancarlos/code-jig/blob/main/.github/workflows/ci.yml ; tests: https://github.com/jeancarlos/code-jig/tree/main/tests |
| test_policy, tests_are_added, tests_documented_added | Met | https://github.com/jeancarlos/code-jig/blob/main/CONTRIBUTING.md |
| warnings, warnings_fixed, warnings_strict | Met | ruff (https://docs.astral.sh/ruff/) in CI, `code-jig analyze` |
| know_secure_design, know_common_errors | Met | https://github.com/jeancarlos/code-jig/blob/main/CONTRIBUTING.md secure design paragraph |
| crypto_* | N/A | no cryptography implemented; sha256 from hashlib only |
| delivery_unsigned | Met | wheel, SBOM (https://www.cisa.gov/sbom) and SHA256SUMS signed with Sigstore (https://www.sigstore.dev/), SLSA (https://slsa.dev/) provenance; PyPI (https://pypi.org/project/code-jig/) gets the attested wheel ; https://github.com/jeancarlos/code-jig/releases |
| vulnerabilities_fixed_60_days, vulnerabilities_critical_fixed | Met | none known open; osv-scanner (https://github.com/google/osv-scanner) in CI |
| no_leaked_credentials | Met | gitleaks (https://github.com/gitleaks/gitleaks) over full history in CI |
| static_analysis, static_analysis_fixed, static_analysis_often | Met | CodeQL (https://codeql.github.com/), ruff (https://docs.astral.sh/ruff/), zizmor (https://github.com/zizmorcore/zizmor) on every push |
| static_analysis_common_vulnerabilities | Met | CodeQL (https://codeql.github.com/) runs its default query suite for Python and GitHub Actions, which includes the security queries for injection, path traversal and unsafe deserialization (https://github.com/jeancarlos/code-jig/blob/main/.github/workflows/security.yml) |
| dynamic_analysis, dynamic_analysis_enable_assertions | Met | ClusterFuzzLite (https://google.github.io/clusterfuzzlite/) with atheris (https://github.com/google/atheris), https://github.com/jeancarlos/code-jig/blob/main/.github/workflows/fuzz.yml |
| dynamic_analysis_unsafe, dynamic_analysis_fixed | N/A | memory-safe language |
