# Scaleway as Carl's host

Type: research
Status: resolved
Blocked by: 

## Question

How does Scaleway compare with Cloudflare Workers + Durable Objects + R2 (see [hosting-small-backend.md](../../../docs/research/hosting-small-backend.md)) for Carl's small backend: serverless containers/functions and their connection-duration limits for 2-hour WebSocket sessions, small instances, Object Storage with lifecycle deletion after 6 months, secrets, EU location, access control for a single owner, static page hosting and pricing at this scale? Also note whether Scaleway GPUs could run a self-hosted speech-to-text model, against Vast.ai. Findings go in `docs/research/scaleway-hosting.md`.

## Answer

Researched 2026-09-25; findings in [scaleway-hosting.md](../../../docs/research/scaleway-hosting.md).

- **Cloudflare is still the better fit.** Scaleway Serverless Containers and
  Functions cap every HTTP request at 60 minutes (inferred to include
  WebSockets; to be tested), so a 2-hour session would be cut, as on Cloud
  Run. A private container needs an `X-Auth-Token` header that a browser
  WebSocket can't send, so owner-only access is weaker.
- **A Scaleway Instance works** (STARDUST1-S ~€0.43/month, DEV1-S ~€6.55,
  plus IPv4 ~€3 and a disk): the same kind of option as Hetzner, EU-owned,
  with all the server upkeep on the owner.
- **Object Storage lifecycle rules** meet the 6-month deletion rule (daily,
  up to 24 h late) for ~€0.48/month at 30 GB. Secrets and EU regions (Paris,
  Amsterdam, Warsaw) are fine.
- **GPU for Parakeet v3:** a Scaleway L4 at €0.79/h billed per minute, about
  €1.75 per session with start/stop automation. Vast.ai is $0.16–0.54/h, but a
  stopped GPU can be rented away and hosts can read files on their machines,
  a poor home for private audio. Self-hosting is a later experiment, not the
  first build.
