# 0005: Public data rule and the deck template

Status: accepted (2026-10-14)

## Decision
Nothing in this repo carries a number measured on a corporate machine, not even as a percentage. Every public claim cites a bench measurement or a public source. The deck (`docs/deck/`) renders from `data.js`, which holds only those. A gitignored `data.local.js` overrides any value.

## Reason to exist
A published usage number becomes the employer's internal metric. The deck must still be presentable with real numbers on the machine where it is shown.

## Data
None. This is a rule, not a measurement.

## Cost
One gitignored file, `data.local.js`. A value missing from both files renders as a visible "fill in `<key>`" badge, so the gaps are obvious.

## Kind
Rule, enforced by review.

## Rejected alternatives
- Anonymised or rounded corporate numbers. Still an internal metric once published.
- Keeping the deck out of the repo. It could not be reviewed or versioned.
