# Step 1: Domain and loading Worker

Type: task
Status: open
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

- [ ] `faktat.vempai.men` opens behind an access pass, and the WebSocket
      connects through `/api/ws`.
- [ ] The loading page is seen on a cold start.
- [ ] The main route fails open.

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
