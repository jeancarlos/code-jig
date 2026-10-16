const RELEASES = "https://github.com/jeancarlos/code-jig/releases"
const TAG = /^v\d+\.\d+\.\d+$/
const FILES = new Set(["code-jig.zip", "SHA256SUMS", "bootstrap.py"])
const TEXT = { "content-type": "text/plain; charset=utf-8" }
const PAGE = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>code-jig</title>
<style>
:root { color-scheme: light dark; --bg: #fff; --fg: #1b1f24; --mute: #57606a; --code: #f3f4f6; --link: #0969da }
@media (prefers-color-scheme: dark) { :root { --bg: #0d1117; --fg: #e6edf3; --mute: #9198a1; --code: #161b22; --link: #4493f8 } }
body { margin: 0 auto; max-width: 42rem; padding: 1.5rem 1rem; background: var(--bg); color: var(--fg); font: 1rem/1.55 system-ui, sans-serif }
h1 { margin: 0 0 .5rem }
h2 { margin: 1.75rem 0 .5rem; font-size: 1.05rem }
pre { margin: 0; padding: .75rem; overflow-x: auto; background: var(--code); border-radius: 6px; font-size: .875rem }
a { color: var(--link) }
.mute { color: var(--mute); font-size: .9rem }
</style>
</head>
<body>
<h1>code-jig</h1>
<p>A config pack that clamps the same tiers, review policy, skills, hooks, git gate and token tracker onto Codex, Claude Code, Antigravity and VS Code Copilot.</p>
<p class="mute">Supported today: Codex. Claude Code, Antigravity and Copilot from the next releases.</p>
<h2>Linux and macOS</h2>
<pre>curl -fsSL https://code-jig.jeansouza.dev/setup | python3 -I - --overlay &lt;path|git-url&gt;</pre>
<h2>Windows (PowerShell)</h2>
<pre>irm https://code-jig.jeansouza.dev/setup | py -3 -I - --overlay &lt;path|git-url&gt;</pre>
<h2>Download, read and run</h2>
<pre>${RELEASES}/latest/download/bootstrap.py
python3 -I bootstrap.py --overlay &lt;path|git-url&gt;</pre>
<p class="mute">This site counts requests for the setup script and release zips: event, version, client type, country. No IP address, user-agent string or install ID is stored. The tool itself sends nothing.</p>
<p><a href="https://github.com/jeancarlos/code-jig">Source on GitHub</a></p>
</body>
</html>
`
const HTML = { "content-type": "text/html; charset=utf-8" }

export function client(ua) {
  const s = (ua || "").toLowerCase()
  if (s.startsWith("curl/")) return "curl"
  if (s.includes("powershell")) return "powershell"
  if (s.startsWith("python-urllib/")) return "python"
  return "other"
}

function count(env, request, event, tag) {
  if (request.method !== "GET") return
  env.INSTALLS?.writeDataPoint({
    blobs: [event, tag, client(request.headers.get("user-agent")), request.cf?.country || ""],
    indexes: [event],
  })
}

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("method not allowed\n", { status: 405, headers: TEXT })
    }
    const { pathname } = new URL(request.url)
    if (pathname === "/") return new Response(PAGE, { headers: HTML })
    if (pathname === "/setup") {
      const upstream = await fetch(`${RELEASES}/latest/download/bootstrap.py`)
      if (!upstream.ok) return new Response("setup is unavailable\n", { status: 502, headers: TEXT })
      count(env, request, "bootstrap", "")
      return new Response(upstream.body, { headers: { ...TEXT, "cache-control": "no-store" } })
    }
    const m = pathname.match(/^\/v\/([^/]+)\/([^/]+)$/)
    if (m && TAG.test(m[1]) && FILES.has(m[2])) {
      if (m[2] === "code-jig.zip") count(env, request, "download", m[1])
      return Response.redirect(`${RELEASES}/download/${m[1]}/${m[2]}`, 302)
    }
    return new Response("not found\n", { status: 404, headers: TEXT })
  },
}
