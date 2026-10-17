import { test } from "node:test"
import assert from "node:assert/strict"
import worker from "./index.mjs"

const BOOTSTRAP = "https://github.com/jeancarlos/code-jig/releases/latest/download/bootstrap.py"

function req(path, method = "GET") {
  return new Request(`https://code-jig.jeansouza.dev${path}`, { method })
}

async function page() {
  return (await worker.fetch(req("/"))).text()
}

test("root serves html", async () => {
  const r = await worker.fetch(req("/"))
  assert.equal(r.status, 200)
  assert.equal(r.headers.get("content-type"), "text/html; charset=utf-8")
  const body = await r.text()
  assert.match(body, /<meta name="viewport"/)
  assert.match(body, /prefers-color-scheme: dark/)
  assert.ok(!body.includes("—"))
})

test("page lists requirements before the commands", async () => {
  const body = await page()
  assert.ok(body.includes("Requires Python 3.11+ and git."))
  assert.ok(body.indexOf("Requires Python 3.11+ and git.") < body.indexOf("curl -fsSL"))
})

test("every command downloads from github.com", async () => {
  const body = await page()
  assert.ok(body.includes(`curl -fsSL ${BOOTSTRAP} | python3 -I -</pre>`))
  assert.ok(body.includes(`curl -fsSL -o bootstrap.py ${BOOTSTRAP}\npython3 -I bootstrap.py</pre>`))
  assert.ok(body.includes(`irm ${BOOTSTRAP} -OutFile bootstrap.py\npy -3 -I bootstrap.py</pre>`))
  for (const [, cmd] of body.matchAll(/<pre>([^<]*)<\/pre>/g)) assert.ok(!/&lt;|&gt;/.test(cmd), cmd)
  assert.ok(!body.includes("/setup"))
})

test("page mentions the manual zip form", async () => {
  const body = await page()
  assert.ok(body.includes("--zip code-jig.zip"))
  const links = [...body.matchAll(/href="([^"]+)"/g)].map((m) => new URL(m[1], "https://code-jig.jeansouza.dev/"))
  assert.ok(links.some((u) => u.origin === "https://github.com" && u.pathname === "/jeancarlos/code-jig/releases/latest"))
})

test("every other path is 404", async () => {
  for (const path of ["/setup", "/bootstrap.py", "/v/v0.11.0/code-jig.zip", "/stats"]) {
    const r = await worker.fetch(req(path))
    assert.equal(r.status, 404, path)
  }
})

test("only GET and HEAD", async () => {
  assert.equal((await worker.fetch(req("/", "POST"))).status, 405)
  assert.equal((await worker.fetch(req("/", "HEAD"))).status, 200)
})
