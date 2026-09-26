# Carl runs in a Scaleway serverless container behind a Cloudflare loading page

Research found Cloudflare Workers + Durable Objects + R2 the best fit for
Carl's server: no connection-length limit and built-in owner-only login. We
chose a Scaleway Serverless Container (Python, scaled to zero, max scale 1)
with Scaleway Object Storage, a password gate and a Cloudflare Worker that
shows a "Starting up…" page during cold starts. This is the setup the owner
already runs and maintains for akaihola/drum-transcribe, so Carl reuses its
code, operations and recovery routine instead of a second platform and
language.

## Consequences

- Scaleway cuts a request at 60 minutes, so the page hands its session over to
  a fresh WebSocket at about 50 minutes, and the limit is measured early in
  the build.
- Session state is saved to the bucket, since memory is lost when the
  container scales down or restarts.
- If the handover or CPU throttling while no page is connected proves
  unworkable, the fallback is a Scaleway Instance (about €3.50 a month,
  always on) running the same container image.
