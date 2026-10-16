import { test, afterEach } from "node:test"
import assert from "node:assert/strict"
import worker, { client } from "./index.mjs"

const realFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = realFetch })

function env() {
  const points = []
  return { points, INSTALLS: { writeDataPoint: (p) => points.push(p) } }
}

function req(path, ua = "curl/8.9.1", method = "GET") {
  return new Request(`https://code-jig.jeansouza.dev${path}`, { method, headers: { "user-agent": ua } })
}

const RELEASES = "https://github.com/jeancarlos/code-jig/releases"

test("zip redirects to the tag and counts a download, query ignored", async () => {
  const e = env()
  const r = await worker.fetch(req("/v/v0.11.0/code-jig.zip?from=v0.10.0&os=linux"), e)
  assert.equal(r.status, 302)
  assert.equal(r.headers.get("location"), `${RELEASES}/download/v0.11.0/code-jig.zip`)
  assert.deepEqual(e.points, [{ blobs: ["download", "v0.11.0", "curl", ""], indexes: ["download"] }])
})

test("sums and bootstrap under a tag redirect without counting", async () => {
  for (const file of ["SHA256SUMS", "bootstrap.py"]) {
    const e = env()
    const r = await worker.fetch(req(`/v/v0.11.0/${file}`), e)
    assert.equal(r.status, 302)
    assert.equal(r.headers.get("location"), `${RELEASES}/download/v0.11.0/${file}`)
    assert.deepEqual(e.points, [])
  }
})

test("bad tags, files and paths are 404 and not counted", async () => {
  for (const path of ["/v/v0.11.0.evil/code-jig.zip", "/v/latest/code-jig.zip", "/v/0.11.0/code-jig.zip",
    "/v/v0.11.0/other.zip", "/v/v0.11.0/../x", "/latest/code-jig.zip", "/stats", "/v/v0.11.0/code-jig.zip/x"]) {
    const e = env()
    const r = await worker.fetch(req(path), e)
    assert.equal(r.status, 404, path)
    assert.deepEqual(e.points, [])
  }
})

test("page lists requirements", async () => {
  const r = await worker.fetch(req("/"), env())
  const body = await r.text()
  assert.ok(body.includes("Requires Python 3.11+ and git."))
  assert.ok(body.indexOf("Requires Python 3.11+ and git.") < body.indexOf("curl -fsSL"))
})

test("page mentions the manual zip form", async () => {
  const body = await (await worker.fetch(req("/"), env())).text()
  assert.ok(body.includes("--zip code-jig.zip"))
  const links = [...body.matchAll(/href="([^"]+)"/g)].map((m) => new URL(m[1], "https://code-jig.jeansouza.dev/"))
  assert.ok(links.some((u) => u.origin === "https://github.com" && u.pathname === "/jeancarlos/code-jig/releases/latest"))
})

test("root serves html and counts nothing", async () => {
  const e = env()
  const r = await worker.fetch(req("/"), e)
  assert.equal(r.status, 200)
  assert.equal(r.headers.get("content-type"), "text/html; charset=utf-8")
  const body = await r.text()
  assert.match(body, /<meta name="viewport"/)
  assert.match(body, /prefers-color-scheme: dark/)
  assert.match(body, /curl -fsSL https:\/\/code-jig\.jeansouza\.dev\/setup \| python3 -I -/)
  assert.match(body, /irm https:\/\/code-jig\.jeansouza\.dev\/setup \| py -3 -I -/)
  assert.ok(body.includes("curl -fsSL -o bootstrap.py https://code-jig.jeansouza.dev/setup\npython3 -I bootstrap.py --overlay &lt;path|git-url&gt;"))
  assert.ok(body.includes("irm https://code-jig.jeansouza.dev/setup -OutFile bootstrap.py\npy -3 -I bootstrap.py --overlay &lt;path|git-url&gt;"))
  assert.ok(!body.includes("\u2014"))
  assert.deepEqual(e.points, [])
})

test("setup serves the bootstrap and counts it", async () => {
  const seen = []
  globalThis.fetch = async (url) => { seen.push(String(url)); return new Response("print(1)\n", { status: 200 }) }
  const e = env()
  const r = await worker.fetch(req("/setup", "Mozilla/5.0 (Windows NT 10.0) WindowsPowerShell/5.1"), e)
  assert.equal(r.status, 200)
  assert.equal(r.headers.get("content-type"), "text/plain; charset=utf-8")
  assert.equal(await r.text(), "print(1)\n")
  assert.deepEqual(seen, [`${RELEASES}/latest/download/bootstrap.py`])
  assert.deepEqual(e.points, [{ blobs: ["bootstrap", "", "powershell", ""], indexes: ["bootstrap"] }])
  assert.ok(!JSON.stringify(e.points).includes("Mozilla"))
})

test("bootstrap.py path is 404", async () => {
  const e = env()
  const r = await worker.fetch(req("/bootstrap.py"), e)
  assert.equal(r.status, 404)
  assert.deepEqual(e.points, [])
})

test("upstream failure is 502 and not counted", async () => {
  globalThis.fetch = async () => new Response("nope", { status: 404 })
  const e = env()
  const r = await worker.fetch(req("/setup"), e)
  assert.equal(r.status, 502)
  assert.deepEqual(e.points, [])
})

test("only GET and HEAD", async () => {
  const r = await worker.fetch(req("/", "curl/8", "POST"), env())
  assert.equal(r.status, 405)
})

test("client mapping keeps no raw user-agent", () => {
  assert.equal(client("curl/8.9.1"), "curl")
  assert.equal(client("Mozilla/5.0 (Windows NT 10.0; Microsoft Windows 10.0.26100) PowerShell/7.5.0"), "powershell")
  assert.equal(client("Python-urllib/3.13"), "python")
  assert.equal(client("Mozilla/5.0 Firefox/140.0"), "other")
  assert.equal(client(null), "other")
})

test("missing binding never breaks a download", async () => {
  const r = await worker.fetch(req("/v/v0.11.0/code-jig.zip"), {})
  assert.equal(r.status, 302)
})

test("HEAD on the zip redirects without counting", async () => {
  const e = env()
  const r = await worker.fetch(req("/v/v0.11.0/code-jig.zip", "curl/8.9.1", "HEAD"), e)
  assert.equal(r.status, 302)
  assert.equal(r.headers.get("location"), `${RELEASES}/download/v0.11.0/code-jig.zip`)
  assert.deepEqual(e.points, [])
})

test("HEAD on setup answers 200 without counting", async () => {
  globalThis.fetch = async () => new Response("print(1)\n", { status: 200 })
  const e = env()
  const r = await worker.fetch(req("/setup", "curl/8.9.1", "HEAD"), e)
  assert.equal(r.status, 200)
  assert.deepEqual(e.points, [])
})
