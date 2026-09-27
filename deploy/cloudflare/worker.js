// Page loads that Carl's container doesn't answer within WAIT_MS (it is
// scaled to zero and starting) get a "Starting up…" page instead of a blank
// tab. Everything else passes through untouched. Copied from
// akaihola/drum-transcribe's loading page; see docs/operations.md.
//
// /api/* never reaches this Worker: a second route with no Worker sends the
// WebSocket, the health poll and the API straight through Cloudflare's proxy.

const WAIT_MS = 2500;

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

export default {
  async fetch(request, env, ctx) {
    const upstream = fetch(request, {redirect: "manual"});
    if (request.headers.get("Sec-Fetch-Mode") !== "navigate") return upstream;
    ctx.waitUntil(upstream.catch(() => {}));  // keep waking the container
    const late = new Promise(r => setTimeout(r, WAIT_MS, null));
    const response = await Promise.race([upstream, late]).catch(() => null);
    return response && response.status < 502 ? response : loading();
  },
};
