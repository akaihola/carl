# Hosting a small backend with streaming connections and secrets

Type: research
Status: claimed
Blocked by: 

## Question

Where could a small personal backend for Carl run, if it needs one: long-lived WebSocket or streaming connections for up to 2 h, holding API keys as secrets, optional storage for recording sessions (tens of GB of audio over 6 months), with low fixed cost and little operations work? Compare e.g. Cloudflare Workers with Durable Objects and R2, Fly.io, Deno Deploy, Google Cloud Run, a small VPS, and a home machine behind a tunnel. Note connection-duration limits, pricing, EU data location and how secrets are handled. Findings go in `docs/research/hosting-small-backend.md`.
