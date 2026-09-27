// Carl's front door. Scanners probe faktat.vempai.men every 10–30 minutes,
// and each request that reached Carl's container would wake it and keep it
// up for about 15 minutes. So a request without an access-pass cookie never
// reaches it: this Worker answers it as Carl's gate would, with the pass form
// for a GET of a page and a 401 for anything else. Only the pass form's own
// POST and requests with the cookie go through. The cookie is only looked
// for here; Carl's gate checks it.
//
// Page loads that Carl's container doesn't answer within WAIT_MS (it is
// scaled to zero and starting) get a "Starting up…" page instead of a blank
// tab. Copied from akaihola/drum-transcribe's loading page; see
// docs/operations.md.
//
// /api/ws never reaches this Worker: a second route with no Worker sends the
// WebSocket straight through Cloudflare's proxy.

import PASS_PAGE from "../../src/carl/pass.html";  // server.py serves the same file

const WAIT_MS = 2500;
const PASS_COOKIE = /(?:^|;\s*)carl_pass=[^;\s]/;  // gate.COOKIE
const PASS_CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'";
const HEADERS = {"Cache-Control": "no-store, no-transform",
                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"};

const LOADING = `<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Starting up…</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #0f1319; color: #e9edf2;
         font: 18px/1.5 "Atkinson Hyperlegible", Verdana, system-ui, sans-serif; }
  main { display: grid; gap: .4em; justify-items: center; text-align: center; padding: 1em; }
  h1 { font-size: 1.6em; margin: 0; }
  p { color: #8894a5; margin: 0; }
  b { color: #d8c38a; font-size: 1.4em; }
</style>
<main>
  <h1>Starting up…</h1>
  <p>Carl was asleep and is waking up. This usually takes under a minute.</p>
  <b id="t">0 s</b>
</main>
<script>
  const t0 = Date.now();
  setInterval(() => t.textContent = Math.round((Date.now() - t0) / 1000) + " s", 1000);
  (async () => {
    for (;;) {
      try { if ((await fetch("/api/health", {cache: "no-store"})).ok) break; } catch {}
      await new Promise(r => setTimeout(r, 2000));
    }
    location.reload();
  })();
</script>
</html>`;

const loading = () => new Response(LOADING, {
  status: 503,
  headers: {"Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store", "Retry-After": "5"},
});

// What Carl's gate answers a request without an access pass (server.py).
const turnAway = (request, url) => request.method === "GET" && !url.pathname.startsWith("/api/")
  ? new Response(PASS_PAGE, {status: 401, headers: {
      ...HEADERS, "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": PASS_CSP}})
  : new Response("An access pass is needed.", {status: 401, headers: {
      ...HEADERS, "Content-Type": "text/plain; charset=utf-8"}});

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const unlocking = request.method === "POST" && url.pathname === "/api/unlock";
    if (!unlocking && !PASS_COOKIE.test(request.headers.get("Cookie") ?? "")) return turnAway(request, url);
    const upstream = fetch(request, {redirect: "manual"});
    // The loading page reloads what it stands in for, so only a GET gets it:
    // the pass form's POST just waits for the container.
    if (request.method !== "GET" || request.headers.get("Sec-Fetch-Mode") !== "navigate") return upstream;
    ctx.waitUntil(upstream.catch(() => {}));  // keep waking the container
    const late = new Promise(r => setTimeout(r, WAIT_MS, null));
    const response = await Promise.race([upstream, late]).catch(() => null);
    return response && response.status < 502 ? response : loading();
  },
};
