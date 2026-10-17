# code-jig Worker

A Cloudflare Worker that serves the preview page at https://code-jig.jeansouza.dev. It is not part of the core, has no dependencies and counts nothing. Every install command on the page downloads from GitHub, so a network that blocks this domain can still install.

`/` is the HTML page, readable on a phone, light and dark. Every other path is a 404, and any method other than `GET` and `HEAD` is a 405. Workers Logs are off (`[observability]` in `wrangler.toml`).

## Test

```sh
node --test worker/index.test.mjs
```

## Deploy

Wrangler is pinned in CONTRIBUTING.md (4.151.1 today). Log in once, then deploy from this folder:

```sh
cd worker
npx wrangler@4.151.1 login
npx wrangler@4.151.1 deploy
```

Before the first deploy, check the domain:

1. `jeansouza.dev` is a zone on the Cloudflare account you log in with.
2. `code-jig.jeansouza.dev` has no DNS record yet. A custom domain route creates its own record and fails if one exists. Note that the `*.jeansouza.dev` wildcard answers any name, so a lookup that resolves does not prove the name is free; look in the DNS dashboard.
3. After deploy, `curl -i https://code-jig.jeansouza.dev/` returns the page. A new name checked too early can stay NXDOMAIN for a while in resolver caches.
