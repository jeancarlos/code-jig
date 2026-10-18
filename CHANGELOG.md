# Changelog

What changed in each release, written for the people who install code-jig. Versions follow [Semantic Versioning](https://semver.org/). The release workflow publishes the section of the tag as the GitHub release notes and refuses a tag without one.

## Unreleased

- `code-jig humanize` cleans Python docstrings and the comments of JavaScript, TypeScript, Java, C, C++, C#, Go, Rust and CSS, and strips model citation leftovers and chatbot openers.
- `code-jig humanize --rewrite` sends machine-sounding comment text to your gateway and writes the reply back. It refuses unsafe replies, never sends the key over plain http off this machine, and reports how many flagged blocks it refused.
- Ten audit findings fixed, each with a regression test.

## 0.12.0 - 2026-10-17

- The release is now built and smoke-tested as a wheel from the release tree, so what you install is exactly what CI tested.
- The GitHub tarball keeps the files OpenSSF Scorecard reads; the release builder still leaves them out of the wheel.

## 0.11.4 - 2026-10-17

- A malformed HTML section no longer crashes `page_text`, and it now fails closed when the parser raises.
- `agnix` installs its binary.

## 0.11.3 - 2026-10-17

- The core rules tell the agent which subagent type to pick for the job.

## 0.11.2 - 2026-10-17

- The README install block pastes without edits and is rewritten by the release job.
- The `web-consensus` challenger sweeps every claim before reporting and errs toward flagging.

## 0.11.1 - 2026-10-17

- Installs come only from GitHub. The Worker serves just the preview page.

## 0.11.0 - 2026-10-16

- The git gate removes AI attribution from outgoing commits on push, and the pre-push hook runs your `codejig.testCommand` and refuses the push when it fails.
- One AI-watermark remover covers files, commit messages and history, with a `remove-ai-attribution` skill as a safety net.
- Install and update work from a downloaded zip, and the installer checks Python and git first.
- Co-author lines are removed only on a tool signal, so people whose names look like tools are kept.
- Upgrade note: run `code-jig install` after upgrading so the new gate is written.
