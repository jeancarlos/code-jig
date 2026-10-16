const RELEASES = "https://github.com/jeancarlos/code-jig/releases"
const TAG = /^v\d+\.\d+\.\d+$/
const FILES = new Set(["code-jig.zip", "SHA256SUMS", "bootstrap.py"])
const TEXT = { "content-type": "text/plain; charset=utf-8" }
const PAGE = `code-jig setup

Linux and macOS:
  curl -fsSL https://code-jig.jeansouza.dev/bootstrap.py | python3 -I - --overlay <path|git-url>

Windows (PowerShell):
  irm https://code-jig.jeansouza.dev/bootstrap.py | py -3 -I - --overlay <path|git-url>

Download, read and run:
  ${RELEASES}/latest/download/bootstrap.py
  python3 -I bootstrap.py --overlay <path|git-url>

This site counts requests for bootstrap.py and release zips: event, version, client type, country.
No IP address, user-agent string or install ID is stored. The tool itself sends nothing.

Source: https://github.com/jeancarlos/code-jig
`

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
    if (pathname === "/") return new Response(PAGE, { headers: TEXT })
    if (pathname === "/bootstrap.py") {
      const upstream = await fetch(`${RELEASES}/latest/download/bootstrap.py`)
      if (!upstream.ok) return new Response("bootstrap.py is unavailable\n", { status: 502, headers: TEXT })
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
