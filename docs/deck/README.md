# Editing the deck

The deck is `docs/deck/index.html`. Public values live in `docs/deck/data.js`, which is committed and holds bench and public numbers only.

Work numbers never go in the repo. They go in `docs/deck/data.local.js`, which is gitignored. Create it next to `index.html`:

```js
window.DECK_LOCAL = {
  work_guardian_share: 0,
  work_cache_hit: "TODO"
};
```

Keys are the names used in `index.html`. Values are placeholders here; put your own on your machine.

Rules:

- Never commit `data.local.js`. It is gitignored; do not force-add it.
- Any yellow "fill in <key> in data.local.js" badge names a key that is still null or missing.
- Open `index.html` in a browser and step through with the arrow keys or a click.
- Add `?all` to the URL to show every slide on one page, for print or PDF.
- Work numbers belong only in `data.local.js`, and only on the machine where you present.
- The published Artifact has no `data.local.js`, so work values show as badges there. That is correct.
