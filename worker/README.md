# setup-harness Worker

A Cloudflare Worker that serves https://setup-harness.jeansouza.dev. It is infrastructure for the install-from-a-release-URL path ([ADR 0027](../docs/adr/0027-install-from-a-release-url.md)), not part of the core. It has no dependencies.

## Routes

| Route | What it does | Counted |
|---|---|---|
| `/` | Plain-text page with the install commands | no |
| `/bootstrap.py` | The latest release's `bootstrap.py`, fetched from GitHub, never cached | `bootstrap` |
| `/v/<tag>/codex-harness.zip` | 302 to the GitHub release asset | `download` |
| `/v/<tag>/SHA256SUMS`, `/v/<tag>/bootstrap.py` | 302 to the GitHub release asset | no |

`<tag>` must look like `v1.2.3`. Anything else is a 404, and any method other than `GET` and `HEAD` is a 405. Only `GET` requests are counted. If GitHub does not answer for `/bootstrap.py`, the Worker returns 502 and counts nothing.

Each count is one Analytics Engine row in the dataset `codex_harness_installs` (binding `INSTALLS`): the event, the tag (empty for `bootstrap`), the client type (`curl`, `powershell`, `python` or `other`) and the Cloudflare country. No IP address, user-agent string or install ID is stored, and Workers Logs are off (`[observability]` in `wrangler.toml`).

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
2. `setup-harness.jeansouza.dev` has no DNS record yet. A custom domain route creates its own record and fails if one exists. Note that the `*.jeansouza.dev` wildcard answers any name, so a lookup that resolves does not prove the name is free; look in the DNS dashboard.
3. After deploy, `curl -i https://setup-harness.jeansouza.dev/` returns the page, and `curl -sI https://setup-harness.jeansouza.dev/v/v0.11.0/codex-harness.zip` returns a 302 to GitHub. A new name checked too early can stay NXDOMAIN for a while in resolver caches.

## Read the counts

The token needs the Account Analytics Read permission. Do not paste it into a command line you keep in shell history; read it from a file or a secret store.

```sh
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_ANALYTICS_TOKEN" \
  --data "SELECT blob1 AS event, blob2 AS tag, blob3 AS client, blob4 AS country, SUM(_sample_interval) AS requests
          FROM codex_harness_installs WHERE timestamp > NOW() - INTERVAL '30' DAY
          GROUP BY event, tag, client, country ORDER BY requests DESC"
```

Analytics Engine keeps data for three months. Cloudflare may sample high volumes, so always sum `_sample_interval`; `COUNT(*)` undercounts. A row is a request, not an install: anyone can send one, and an install, an upgrade and a rollback look the same.
