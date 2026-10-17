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
<p>Requires Python 3.11+ and git.</p>
<h2>Linux and macOS</h2>
<pre>curl -fsSL https://github.com/jeancarlos/code-jig/releases/latest/download/bootstrap.py | python3 -I - --overlay &lt;path|git-url&gt;</pre>
<p>Or download, read and run:</p>
<pre>curl -fsSL -o bootstrap.py https://github.com/jeancarlos/code-jig/releases/latest/download/bootstrap.py
python3 -I bootstrap.py --overlay &lt;path|git-url&gt;</pre>
<h2>Windows (PowerShell)</h2>
<pre>irm https://github.com/jeancarlos/code-jig/releases/latest/download/bootstrap.py -OutFile bootstrap.py
py -3 -I bootstrap.py --overlay &lt;path|git-url&gt;</pre>
<p>Everything downloads from GitHub. No one-liner allowed? Download <code>code-jig.zip</code>, <code>SHA256SUMS</code> and <code>bootstrap.py</code> from the <a href="https://github.com/jeancarlos/code-jig/releases/latest">GitHub release</a>, then run <code>py -3 -I bootstrap.py --zip code-jig.zip --overlay &lt;path&gt;</code> (<code>python3 -I</code> on Linux and macOS).</p>
<p><a href="https://github.com/jeancarlos/code-jig">Source on GitHub</a></p>
</body>
</html>
`
const HTML = { "content-type": "text/html; charset=utf-8" }

export default {
  async fetch(request) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("method not allowed\n", { status: 405, headers: TEXT })
    }
    if (new URL(request.url).pathname === "/") return new Response(PAGE, { headers: HTML })
    return new Response("not found\n", { status: 404, headers: TEXT })
  },
}
