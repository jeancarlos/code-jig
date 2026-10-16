# 0002: Overlay slots, core_writable and clean-room upstream

Status: accepted (2026-10-14)

## Decision
The pack has a shared core and an overlay with fixed slots. The overlay is a separate directory, kept in its own private repo if needed. `core_writable` says whether anything may edit the core. The core accepts only clean-room contributions: nothing copied from a private overlay or an employer.

## Reason to exist
Personal and employer-specific content must stay out of the shared core. A pinned core must stay verifiable. Without a boundary, local edits drift into the core and cannot be told apart from upstream.

## Data
None needed. The one concrete input is the list of security triggers that must stay in the core.

## Cost
One constraint on the `improve` skill: it honours `core_writable`. One `doctor` check: the core tree is unchanged when `core_writable = false`. `doctor` also FAILs a core that is not a git checkout or cannot be read. A release install (ADR 0027) is checked by its `VERSION` digest instead.

## Kind
Script, with a rule for people.

## Rejected alternatives
- One flat config tree. No way to separate shareable from private content.
- Copying the core into each overlay. Drift, and no way to pin a version.
