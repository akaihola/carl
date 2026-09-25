# Hosting a small backend with streaming connections and secrets

Type: research
Status: resolved
Blocked by: 

## Question

Where could a small personal backend for Carl run, if it needs one: long-lived WebSocket or streaming connections for up to 2 h, holding API keys as secrets, optional storage for recording sessions (tens of GB of audio over 6 months), with low fixed cost and little operations work? Compare e.g. Cloudflare Workers with Durable Objects and R2, Fly.io, Deno Deploy, Google Cloud Run, a small VPS, and a home machine behind a tunnel. Note connection-duration limits, pricing, EU data location and how secrets are handled. Findings go in `docs/research/hosting-small-backend.md`.

## Answer

See [docs/research/hosting-small-backend.md](../../../docs/research/hosting-small-backend.md).

- Every managed host drops long WebSockets sometimes (deploys, platform restarts, eviction, idle close), so Carl must reconnect cleanly whatever the host; heartbeats are needed through quiet stretches and pause (Fly.io closes after 60 s idle).
- Vercel (300 s on Hobby, 800–1800 s on Pro) and Cloud Run (60 min max per request) fail the 2-hour test as designed: the speech-to-text connection would be re-opened mid-session.
- Cloudflare Workers + Durable Objects + R2 fits every requirement for $0–5 a month: no hard connection limit, `eu` jurisdiction for objects and buckets, hidden secrets, R2 lifecycle expiry, Cloudflare Access for owner-only login, and the static page on the same host. The outbound WebSocket to the speech-to-text vendor can't hibernate, but at Carl's scale that stays inside the included allowance.
- Fly.io (~$2–3.3 a month for one small EU machine, Tigris storage with EU buckets and lifecycle rules) and a Hetzner VPS (CX23 €5.49 + €0.50 IPv4 in Helsinki, but listed "currently unavailable" on 2026-09-25) run any language with no duration limits; the VPS brings the most operations work.
- Deno Deploy is free and has an `eu` region, but it may evict running instances and has no object storage.
- A home machine behind Cloudflare Tunnel + Access is nearly free and keeps audio at home, but Carl depends on that machine and connection. Tailscale Funnel is beta and has no login in front.
- Lifecycle rules for the 6-month deletion of recording sessions exist on R2, Tigris, Hetzner Object Storage and Cloud Storage (which soft-deletes for 7 more days by default). Tens of GB costs cents a month.
- GitHub Pages (free for public repos) still works for the page; Cloudflare static assets are a free alternative that can sit behind the same Access login.
