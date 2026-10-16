# Runbook: custom CA certificates and networked tools

Networks that inspect TLS re-sign traffic with their own root certificate. Codex and every tool it runs must trust that root, and each runtime reads it from a different place.

## Codex itself

Codex reads a PEM bundle from `CODEX_CA_CERTIFICATE`, falling back to `SSL_CERT_FILE` (`codex-rs/http-client/src/custom_ca.rs`). Export it in the shell profile that starts Codex:

```sh
export CODEX_CA_CERTIFICATE=/path/to/root-ca.pem
```

`codex doctor` (Codex's own, not code-jig's) prints the proxy and certificate variables it sees and probes the connection. Run it first when Codex cannot reach the model.

## Tools Codex runs

Commands inherit the shell environment unless `shell_environment_policy` in `config.toml` narrows it. Set each runtime's variable in the same profile:

| Runtime | Variable or setting |
|---|---|
| Python tools (`az`, `pip`, `requests`) | `REQUESTS_CA_BUNDLE`, and `SSL_CERT_FILE` |
| Node tools (`npm`, most MCP servers) | `NODE_EXTRA_CA_CERTS` |
| git over HTTPS | `git config --global http.sslCAInfo /path/to/root-ca.pem`, or Git Credential Manager with the system store |
| curl | `CURL_CA_BUNDLE`, or the system store |

On Windows, most of these read the Windows certificate store once the root is installed there; the variables are still needed for Python and Node.

## code-jig check-sources

`check-sources` (used by the `web-consensus` skill) fetches every cited URL with Python's `urllib`. It honours `HTTPS_PROXY`, `HTTP_PROXY` and `NO_PROXY`, uses the system certificate store on Windows and `SSL_CERT_FILE` elsewhere, and sends a plain browser-like User-Agent. Only `http` and `https` URLs on public addresses are requested: a URL or redirect to a loopback, private, link-local or reserved address is refused, and without a proxy the connected address is checked again. Behind a proxy, a host this machine cannot resolve is refused (`cannot confirm ... is public`), because the proxy might reach an internal site with that name; if every source is refused this way, the machine has no DNS of its own and `check-sources` cannot be used there. Inside a sandbox without network it stops at once and asks for an escalated run, so one Guardian review covers every URL.

## The sandbox and Guardian

Every tier runs Codex's sandbox, which blocks network access and writes outside the workspace. So `git fetch`, `git push`, `az ...` and package installs ask to leave the sandbox, and Guardian reviews each request. That is the intended trade: each review costs input tokens (`code-jig tokens` shows how many), and in exchange nothing reaches the network unseen.

- If the same routine command keeps escalating, describe in the overlay's `guardian-policy.md` when it is fine, for example "fetching from and pushing feature branches to the team's git host at `<host>` is low risk".
- Add `forbidden` rules for what must never happen, such as force pushes or deleting repositories. The personal example overlay forbids `git push --force`.
- Do not turn on `sandbox_workspace_write.network_access` to save reviews: the sandboxed agent could then send anything anywhere.
- CLIs that cache tokens in the home directory (`~/.azure`, `~/.config/gh`) cannot refresh them from inside the sandbox. Log in from your own terminal before starting Codex.

## Secrets in the environment

By default Codex passes the whole environment to commands, tokens included. If personal access tokens live in environment variables, prefer each tool's own credential store, such as Git Credential Manager or `az login`, over exporting the token.

## Azure Repos and the az CLI

- Clone and push over HTTPS with Git Credential Manager; it handles Entra ID sign-in and the system certificate store.
- `az repos pr create`, `az repos pr list` and `az pipelines runs show` (from the `azure-devops` extension) give Codex PRs and pipeline status as plain commands, reviewed by Guardian like any other.
- An Azure DevOps MCP server exposes the same data as tools. It is an extra Node package and its tool list costs context on every request; check whether you are allowed to install it, and enable only the domains you use.
