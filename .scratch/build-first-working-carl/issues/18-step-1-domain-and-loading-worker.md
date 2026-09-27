# Step 1: Domain and loading Worker

Type: task
Status: resolved
Blocked by: 17

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). The
[First working Carl spec](../../first-working-carl/spec.md#hosting) is the
source of truth. drum-transcribe's `docs/loading-page-plan.md` and
`deploy/cloudflare/worker.js` are the model. It needs the Cloudflare
credentials (`CLOUDFLARE_*`).

## What to build

- the proxied CNAME `faktat.vempai.men` in the Cloudflare `vempai.men` zone,
  pointing at the container endpoint, with zone SSL "Full", and the domain
  bound to the container so Scaleway keeps its own certificate for it;
- the loading Worker on `faktat.vempai.men/*`: "Starting up…" with a seconds
  counter after 2.5 s without an answer, polling `/api/health`, reloading
  once the container is up, and failing open;
- the Worker-free route `faktat.vempai.men/api/*` for the WebSocket, the
  health poll and the API;
- `npx wrangler deploy` and the off switch (the DNS record back to "DNS
  only") in the operations doc.

## Done when

- [x] `faktat.vempai.men` opens behind an access pass, and the WebSocket
      connects through `/api/ws`.
- [x] The loading page is seen on a cold start.
- [x] The main route fails open.

## Comments

- 2026-09-27: `deploy/cloudflare/worker.js` and `wrangler.toml` are
  written, from drum-transcribe's Worker: the Worker `faktat-front` on
  `faktat.vempai.men/*`, polling `/api/health`, in Carl's dark colours.
  Tested locally with `wrangler dev --local-upstream` in front of a
  stand-in that took 8 s to wake: Chromium got "Starting up…" after 2.5 s
  with the counter running, and the page reloaded into the app once the
  stand-in answered. The zone's SSL mode is already "Full", and no
  `faktat` record or route exists yet. Nothing is deployed: it waits for
  the container (ticket 17). The steps are 6 and 7 of the first-time
  setup in `docs/operations.md`.
- 2026-09-27: Deployed with the owner's approval of `wrangler deploy`: the
  proxied CNAME `faktat.vempai.men` to the container's endpoint, the
  domain bound to the container, the Worker `faktat-front` on
  `faktat.vempai.men/*` (failing open) and the Worker-free route
  `faktat.vempai.men/api/*`. The page opens behind the access pass, and
  the WebSocket connects through `/api/ws`: the 2-hour connection test and
  a smoke session with speech ran through it. On a real cold start at
  16:08 UTC the Worker answered with "Starting up…" after 3.0 s, and
  `/api/health` answered after 9.9 s ([ticket 02's
  Answer](02-step-1-skeleton-in-the-cloud.md#answer)). Everything behind
  the gate is sent `Cache-Control: private, no-cache, no-transform`, so
  Cloudflare neither caches it nor injects its analytics beacon.
