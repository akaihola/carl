# Hosting a small backend for Carl

Research for the ticket *Hosting a small backend with streaming connections
and secrets* (`.scratch/first-working-carl/issues/05-hosting-small-backend.md`),
compiled 2026-09-25. It answers one question: **if Carl needs a server, where
could it run?** Whether Carl needs one at all, and what it would do, is ticket
06 (*What runs in the browser and what runs on a server*). Which option is
chosen is ticket 13 (*Hosting and secrets*).

## How this was researched, and how far to trust it

- Page fetches worked this time. Claims marked **[verified]** were read on
  2026-09-25 from the vendor's own documentation or pricing page, listed under
  *Sources*.
- **[search]** marks a figure that came from a search-engine summary or a
  secondary site because the primary page loads its prices with JavaScript
  and could not be read. Treat these as likely but check them before relying
  on them.
- **[forum]** marks a statement by vendor staff on the vendor's community
  forum rather than in the documentation.
- Prices are list prices in USD or EUR, excluding VAT. Finnish VAT (25.5%)
  applies on top where the vendor charges it.

## What Carl would ask of a backend

These are the requirements from the ticket, stated as tests an option has to
pass:

1. **Long connections.** One connection from the owner's phone to the server
   and one from the server to the speech-to-text vendor, each open for a whole
   session: up to about 2 hours, with quiet stretches while the table is
   silent or Carl is on pause.
2. **Secrets.** Provider API keys stay on the server and out of the page and
   the repo.
3. **Optional storage for recording sessions.** A few tens of GB of audio in
   total over 6 months, deleted automatically 6 months after recording.
   For scale: speech in Opus at 32 kbit/s is about 14 MB an hour, and raw
   16 kHz 16-bit PCM is about 115 MB an hour, so "tens of GB" is hundreds of
   hours even uncompressed.
4. **Low fixed cost and little operations work.**
5. **Single-owner access.** Only the owner should be able to reach it.
6. **EU data location** is preferable (the owner is in Finland).

## Summary

1. **Every managed option drops long connections sometimes**, so Carl has to
   reconnect cleanly whatever the host. Cloudflare disconnects all WebSockets
   when new code is deployed and when it restarts its own servers; Deno Deploy
   may evict a running instance; Fly.io restarts machines on deploy. The
   difference is how often: on Cloudflare, Fly.io, a VPS or a home machine it
   is occasional, while on Cloud Run a request is cut at **60 minutes at most**
   and on Vercel at **5 minutes (Hobby) or 13–30 minutes (Pro)**.
2. **Vercel and Cloud Run fail the 2-hour test as designed.** Both would force
   Carl to drop and re-open the speech-to-text connection mid-session (every
   5 minutes on Vercel Hobby), and a reconnect may land on a different
   instance that holds none of the session's state.
3. **Cloudflare Workers + Durable Objects + R2 fits the requirements most
   closely at the lowest cost.** No hard limit on connection length, EU
   jurisdiction for both compute state and storage, hidden secrets,
   R2 lifecycle rules that delete after N days, Cloudflare Access for
   single-owner login, and static page hosting in the same place. The
   Workers Paid plan is **$5 a month** and would cover Carl's use with room
   to spare; the free plan may also be enough. The catch is that the
   connection to the speech-to-text vendor is an outbound WebSocket, which
   **keeps the Durable Object in memory and billed** (it cannot hibernate).
   At Carl's scale that is well inside the included allowance.
4. **Fly.io and a Hetzner VPS are the "ordinary server" options.** Both run
   any long-lived process with no platform duration limit, in the EU, for
   about **$2–6 or €6 a month**. Fly.io handles deploys, TLS and secrets but
   closes a connection after **60 s with no data** (staff statement) and has
   no free allowance. A VPS has no platform limits at all but leaves patching,
   TLS, secrets and access control to the owner.
5. **Object storage with automatic deletion is available almost everywhere.**
   R2, Tigris (Fly.io's partner), Google Cloud Storage and Hetzner Object
   Storage all support S3-style lifecycle rules that expire objects after a
   number of days. Vercel Blob and Deno Deploy have no such rule that I found.
   At 30 GB the cost is **cents to a few euros a month**.
6. **A home machine behind Cloudflare Tunnel is nearly free and keeps the
   audio at home**, but Carl then depends on that machine and the home
   connection being up. Tailscale Funnel works too, but it is in beta and
   publishes a public URL with no login in front of it.
7. **Static page hosting is solved.** GitHub Pages worked for the previous
   Carl. Cloudflare can also serve the page free, from the same place as a
   Worker backend and behind the same Access login.

## Comparison at a glance

| Option | Longest connection | Idle cut-off | Fixed cost / month (Carl's scale) | EU location | Object storage with expiry | Owner-only access |
|---|---|---|---|---|---|---|
| Cloudflare Workers + Durable Objects + R2 | No hard limit; dropped on deploy and on Cloudflare restarts | Cloudflare closes idle WebSockets (duration not published); send heartbeats | $0 (free plan) or $5 (Workers Paid) | Durable Objects and R2 `eu` jurisdiction | R2 lifecycle rules | Cloudflare Access (free plan) |
| Fly.io | No platform limit; dropped on deploy | 60 s with no data [forum] | ~$2–3.3 for one small always-on machine | ams, arn, cdg, fra (lhr is not EU) | Tigris lifecycle rules, EU-only buckets | Not built in |
| Deno Deploy | No stated limit; instance may be evicted | App may stop after 5 s–10 min with no traffic; WebSocket data keeps it alive | $0 (Free) | Region `eu` | None built in | Not built in |
| Google Cloud Run | **60 min** per request | — | ~$0 inside the free tier | europe-north1 (Finland) | Cloud Storage lifecycle rules | IAP on the service |
| Vercel | **300 s (Hobby)**, 800 s or 1800 s beta (Pro) | — | $0 Hobby, $20 Pro | Function region arn1, fra1 etc. (default is US) | Vercel Blob, no expiry rule found | Deployment Protection doesn't cover production domains by default |
| Hetzner VPS | No platform limit | None from the platform | ~€6 (CX23 €5.49 + IPv4 €0.50) | Helsinki, Nuremberg, Falkenstein | Hetzner Object Storage lifecycle rules (~€5–6.50 base) | Owner sets it up (e.g. behind Cloudflare Access) |
| Home machine + tunnel | No platform limit; Cloudflare restarts can drop it | Cloudflare idle close as above | ~$0 plus electricity | At home in Finland | Local disk, owner's own deletion job | Cloudflare Access (free) or none (Tailscale Funnel) |

## Cloudflare Workers, Durable Objects and R2 [verified]

**Shape.** A Worker takes the phone's WebSocket and hands it to a Durable
Object, one per session. The Durable Object opens the outbound WebSocket to
the speech-to-text vendor, calls the model providers, and can write audio to
R2.

**Connection limits.**

- "There is no hard limit on duration for HTTP-triggered Workers. As long as
  the client remains connected, the Worker can continue processing." Network
  waiting does not count toward CPU time. The CPU limit per request is 10 ms
  on the free plan and 30 s by default (up to 5 min) on Workers Paid.
- Each invocation may have at most six connections waiting for response
  headers at once; outbound WebSockets count toward that.
- "Code updates disconnect all WebSockets. Deploying a new version restarts
  every Durable Object." Separately, "when Cloudflare releases new code to its
  global network, we may restart servers, which terminates WebSockets
  connections."
- Idle: "Cloudflare will close a WebSocket connection when no data is
  transmitted in either direction for a period of time"; the period is not
  stated, and Cloudflare advises a client-side heartbeat.
- **The outbound connection to the speech-to-text vendor cannot hibernate.**
  "Hibernation is only supported when a Durable Object acts as a WebSocket
  server. Outgoing WebSockets do not hibernate." An outbound WebSocket keeps
  the object in memory for up to 15 minutes without other events; after that
  "the connection stops preventing eviction (the connection itself continues
  operating)" and normal eviction after 70–140 s of no incoming events
  applies. While Carl streams audio from the phone, incoming messages keep
  the object alive anyway. In a long quiet stretch (for example on pause) the
  object could be evicted, so Carl would need either a heartbeat or to
  close and re-open the vendor connection.

**Pricing.**

- Workers Paid: **$5 a month minimum**, including 10 million requests and
  30 million CPU-ms.
- Durable Objects on Workers Paid: 1 million requests and 400,000 GB-s of
  duration included per month. Duration is billed on a fixed 128 MB, so an
  object held in memory for a 2-hour session uses 7,200 s × 0.125 GB =
  **900 GB-s**, and the allowance covers about 440 such hours a month.
  Incoming WebSocket messages are billed at 20:1, so an audio chunk every
  100 ms for 2 hours (72,000 messages) is 3,600 billed requests.
- Durable Objects are also on the **free plan** (SQLite-backed only):
  100,000 requests and 13,000 GB-s a day, which is about 28 object-hours a
  day. The free plan's 10 ms CPU per request is the tighter constraint.
- R2: $0.015 per GB-month, with 10 GB-month, 1 million writes and 10 million
  reads free each month, and no egress fees. At 30 GB stored that is about
  **$0.30 a month**.

**EU location.**

- Durable Objects: `env.MY_DURABLE_OBJECT.jurisdiction("eu")` restricts the
  objects to the EU. The object ID is still "logged outside of the specified
  jurisdiction for billing and debugging purposes."
- R2: a bucket created with jurisdiction `eu` "guarantee[s] objects in a
  bucket are stored within" the EU; this cannot be changed after creation.
  A location hint (`weur`) is only best effort.
- The Worker itself runs wherever the request enters Cloudflare's network.

**Secrets.** `wrangler secret put <KEY>`; "secret values are not visible
within Wrangler or Cloudflare dashboard after you define them." Setting one
deploys a new version, which disconnects open WebSockets.

**Storage expiry.** R2 lifecycle rules with `Expiration: { Days: N }`, set in
the dashboard, with Wrangler or through the S3 API. Objects are "typically
removed from a bucket within 24 hours" of their expiry time.

**Access control.** Cloudflare Access can require login before a
`workers.dev` URL or a custom domain, and the Worker can read the signed-in
identity. Zero Trust has a free plan (50 users per Cloudflare's plan page
[search]). Access sessions last from 15 minutes to one month (default
24 hours), so the owner would log in about once a month at most.

**Operations.** No servers. Deploy with Wrangler. The price of that is the
Workers runtime: JavaScript/TypeScript (or WebAssembly), not arbitrary
processes.

## Fly.io [verified unless marked]

**Shape.** A container (any language) on a Fly Machine, behind Fly's proxy.

**Connection limits.**

- No documented platform limit on connection length.
- Idle: "If no data is received or sent within 60 seconds, the connection
  will be closed," which a Fly staff member says "isn't well documented"
  [forum]. A heartbeat avoids it.
- With `auto_stop_machines`, the proxy checks "every few minutes" and stops a
  single machine "if the Machine has no traffic (a load of 0)". The docs don't
  say whether an open WebSocket counts as load; running one always-on machine
  avoids the question.
- Deploys restart machines, which drops open connections.

**Pricing.** Per-second billing, no ongoing free allowance ("adding a card
ends the free trial"; the trial is 2 VM-hours or 7 days). shared-cpu-1x in
Amsterdam (price multiplier 1.0): **256 MB $2.02, 512 MB $3.32, 1 GB $5.91 a
month** if always on. Stockholm, Frankfurt, Paris and London cost 1.21 times
as much. A stopped machine costs $0.15 per GB of root filesystem a month.
A dedicated IPv4 is $2 a month; European egress is $0.02 per GB.

**EU location.** Regions ams (Amsterdam), arn (Stockholm), cdg (Paris),
fra (Frankfurt); lhr (London) is outside the EU.

**Secrets.** "Stored in an encrypted vault", injected as environment
variables at boot; "we do not allow read access to the plain-text values of
secrets."

**Storage expiry.** Fly's object storage partner is Tigris: $0.02 per
GB-month with 5 GB free and no egress fees (**about $0.50 a month** at 30 GB),
lifecycle rules with `Expiration: { Days: N }`, and buckets that can be kept
in the EU (multi-region EUR, ams and fra, or a single region).

**Access control.** Nothing built in; Carl would need its own login or
Cloudflare in front.

## Deno Deploy [verified]

**Shape.** Serverless TypeScript on the new Deno Deploy. Deploy Classic shuts
down on 2026-07-20, so only the new platform counts.

**Connection limits.** "The application remains alive until no new incoming
requests are received or responses ... are sent for a period of time. The
exact timeout is between 5 seconds and 10 minutes. WebSocket connections that
actively transmit data (including ping/pong frames) also keep the application
alive." But "an isolate may shut down even if the application is actively
receiving traffic" (scale-down, resource pressure, infrastructure updates),
and "clients making long-running requests should be prepared to handle these
disruptions and reconnect."

**Pricing.** Free: 1 million requests, 20 GiB egress, 10 CPU-hours and
150 GiB-hours of memory a month. Pro: $20 a month.

**EU location.** Two regions, `us` and `eu`.

**Secrets.** Environment variables marked secret are "never visible in the UI
after creation".

**Storage expiry.** No object storage. Deno KV has key expiry but is not meant
for audio; recordings would go to an external S3-style store.

**Access control.** Nothing built in that I found.

## Google Cloud Run [verified]

**Shape.** A container that scales to zero.

**Connection limits.** The request timeout is 5 minutes by default "and can be
extended up to 60 minutes (3600 seconds)", and WebSockets are requests:
"Increase the request timeout period to the maximum duration you would like to
keep the WebSockets stream open, for example 60 minutes." So **a 2-hour
session needs at least one reconnect**, and "new WebSockets requests could
still potentially connect to different instances" even with session
affinity.

**Pricing.** "A Cloud Run instance that has any open WebSocket connection is
considered active, so CPU is allocated and the service is billed as
instance-based billing." Instance-based free tier: 240,000 vCPU-seconds and
450,000 GiB-seconds a month (then $0.000018 per vCPU-second and $0.000002 per
GiB-second in Tier 1). A 2-hour session on 1 vCPU uses 7,200 vCPU-seconds,
so about 33 such sessions a month are free. europe-north1 (Finland) is Tier 1.

**EU location.** europe-north1 is in Finland; several other EU regions.

**Secrets.** Secret Manager: 6 active secret versions and 10,000 access
operations a month free.

**Storage expiry.** Cloud Storage lifecycle rules with a `Delete` action and
an age condition. By default a deleted object is soft-deleted and kept for
**7 days**, so real deletion is 6 months plus a week unless soft delete is
turned off. The always-free 5 GB applies only in three US regions.

**Access control.** IAP can be enabled directly on a Cloud Run service,
including for projects outside a Google organization.

**Operations.** Low per-service, but a Google Cloud project, billing account
and IAM setup around it.

## Vercel [verified]

**Shape.** Vercel Functions with Fluid compute.

**Connection limits.** "WebSockets are available in Beta on all plans," but
"WebSocket connections close when a Vercel Function reaches its maximum
duration": **300 s on Hobby**; on Pro 300 s by default, 800 s maximum and
1,800 s in beta. A 2-hour session would reconnect every 5 minutes on Hobby,
and each reconnect "may connect to a different instance". Durable state has
to go to an external store.

**Pricing.** Hobby is free and limited to "non-commercial, personal use"; Pro
is billed per seat and includes $20 of usage credit a month. A WebSocket is
billed as function time for as long as it is open.

**EU location.** Functions default to iad1 (Washington, D.C.); arn1
(Stockholm), fra1 and others can be chosen.

**Storage expiry.** Vercel Blob can be created in any of 19 regions; its docs
describe no lifecycle expiry.

**Access control.** Deployment Protection's recommended "Standard Protection"
"protects all domains except production domains". Password Protection is a
$20-a-month add-on on Pro.

## A small VPS: Hetzner Cloud [verified unless marked]

**Shape.** A Linux server Carl's backend runs on as an ordinary process.

**Connection limits.** None from the platform. If the server sits behind
Cloudflare's proxy (for TLS and Access), Cloudflare's idle close and restarts
apply as above.

**Pricing.** After Hetzner's 2026-06-15 price adjustment, **CX23 (2 vCPU,
4 GB RAM, 40 GB disk) is €5.49 a month** and CAX11 (Arm) €5.99, excluding VAT,
in Germany and Finland, with 20 TB of traffic. A primary IPv4 is €0.50 a
month; IPv6 is free. On 2026-09-25 Hetzner's product page listed both CX23
and CAX11 as "currently unavailable", so availability may be the constraint
rather than price.

**EU location.** Helsinki (HEL1), Nuremberg and Falkenstein.

**Secrets.** Up to the owner (an environment file readable only by the service,
systemd credentials, etc.).

**Storage expiry.** Hetzner Object Storage in HEL1, NBG1 or FSN1 supports
lifecycle policies whose `Expiration` rule deletes objects after N days. It
has a monthly base price per account that includes 1 TB of storage and 1 TB
of egress. The base price loads dynamically on Hetzner's page; it launched at
€4.99 and is reported as €6.49 after April 2026 [search]. For tens of GB the
server's own 40 GB disk plus a daily deletion job would also do.

**Access control.** Up to the owner; the simplest is to put the server behind
Cloudflare (proxied DNS) and Cloudflare Access.

**Operations.** The most of any option: OS updates, TLS (e.g. Caddy), a
process supervisor, firewall and backups.

## A home machine behind a tunnel [verified]

**Shape.** Carl's backend runs on a machine at the owner's home. A tunnel
makes it reachable from the phone without opening ports.

- **Cloudflare Tunnel**: `cloudflared` "creates outbound-only connections to
  Cloudflare's global network". It combines with Cloudflare Access for an
  owner-only login, and Cloudflare's WebSocket idle close and restarts apply.
  Tunnel and Access are both in the Zero Trust free plan.
- **Tailscale Funnel**: "currently in beta", "available for all plans"
  (Personal is free), only on ports 443, 8443 and 10000, TLS only, with
  "non-configurable bandwidth limits". The relay cannot decrypt traffic.
  Funnel publishes a **public** URL with no login in front, so Carl would need
  its own. Plain Tailscale (no Funnel) would keep it private but requires the
  Tailscale app on the phone, which breaks "no app install" for the owner's
  phone.

**Cost.** No hosting fee; electricity and a machine that is on during
sessions. Audio upload at speech bitrates is small.

**EU location.** The owner's home in Finland.

**Storage expiry.** Local disk plus the owner's own deletion job; no provider
lifecycle rules.

**Operations.** Low if the machine already runs, but Carl stops working
whenever the machine, its power or the home connection is down.

## Static page hosting [verified]

- **GitHub Pages** is free for public repositories on GitHub Free; private
  repositories need GitHub Pro or higher. The previous Carl was a static page
  on GitHub Pages that opened a WebSocket straight from the browser to the
  Gemini Live API, with the owner's key in `localStorage`, and "there was no
  server" (see [previous-carl-lessons.md](previous-carl-lessons.md)).
- **Cloudflare Workers static assets / Pages**: "requests to static assets are
  free and unlimited" on free and paid plans. The page, the Worker backend and
  the Access login can sit on one hostname.

## Implications for Carl

These are observations for tickets 06 and 13, not decisions.

- **Reconnecting is a requirement whatever the host.** Every managed option
  documents cases where it drops a WebSocket (deploys, platform restarts,
  eviction, idle close). Carl's page and backend need to reconnect without
  losing the session, and the listening indicator needs a state for it.
  This fits the existing *Listening indicator* definition ("can't hear or
  check (connection lost…)").
- **Heartbeats matter during quiet stretches and pause.** Fly.io closes idle
  connections after 60 s, Cloudflare after an unpublished period, and a
  Durable Object with nothing but an outbound WebSocket can be evicted after
  15 minutes. If Carl hears and sends nothing on pause, either something must
  still flow or Carl must close and re-open connections around the pause.
- **Vercel and Cloud Run would turn every session into many short ones.**
  With a 5-minute (Vercel Hobby) or 60-minute (Cloud Run) cap, the
  speech-to-text connection would be re-opened mid-session, which risks
  losing words and speaker labels at the seam.
- **Cloudflare covers every requirement on one account for $0–5 a month**:
  long connections, EU jurisdiction for state and recordings, hidden secrets,
  lifecycle expiry, owner-only login and the page itself. Its constraint is the
  Workers runtime (JavaScript/TypeScript) and a vendor SDK that may assume
  Node.js.
- **A plain server (Fly.io or Hetzner) keeps the most freedom** of language
  and SDKs and has no duration limits, at a few euros a month. It adds the
  60-second idle rule (Fly.io) or all the operations work (VPS).
- **The 6-month deletion rule for recording sessions maps directly onto
  bucket lifecycle rules** (R2, Tigris, Hetzner, Cloud Storage), with two
  caveats to write down: deletion happens "within 24 hours" of expiry on R2,
  and Cloud Storage keeps soft-deleted objects 7 more days by default. The
  recording session's raw transcript and model-call logs need the same rule
  as its audio.
- **Storage cost is not a deciding factor.** Tens of GB cost cents a month on
  R2 or Tigris and fit on a small VPS's disk.
- **A backend is optional for hosting the page.** The page can stay on
  GitHub Pages or move next to the backend; whether a backend is needed at all
  depends on whether keys can stay out of the page some other way, which is
  ticket 06's question.

## Sources

Cloudflare:

- Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- Workers pricing: https://developers.cloudflare.com/workers/platform/pricing/
- Workers secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- Durable Objects WebSockets: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- Durable Objects lifecycle: https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/
- Durable Objects pricing: https://developers.cloudflare.com/durable-objects/platform/pricing/
- Durable Objects data location: https://developers.cloudflare.com/durable-objects/reference/data-location/
- R2 pricing: https://developers.cloudflare.com/r2/pricing/
- R2 lifecycle rules: https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- R2 data location: https://developers.cloudflare.com/r2/reference/data-location/
- WebSockets through Cloudflare (idle close, restarts): https://developers.cloudflare.com/network/websockets/
- Access on workers.dev: https://developers.cloudflare.com/workers/configuration/routing/workers-dev/
- Access session durations: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- Zero Trust plans (free plan, 50 users [search]): https://www.cloudflare.com/plans/zero-trust-services/ ;
  https://developers.cloudflare.com/cloudflare-one/setup/
- Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/
- Static assets billing: https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/ ;
  https://developers.cloudflare.com/pages/functions/pricing/

Fly.io and Tigris:

- Pricing: https://docs.fly.io/about/pricing/
- Free trial: https://docs.fly.io/about/free-trial/
- Regions: https://docs.fly.io/reference/regions/
- Secrets: https://docs.fly.io/apps/secrets/
- Autostop: https://docs.fly.io/reference/fly-proxy-autostop-autostart/
- 60-second idle timeout [forum]: https://community.fly.io/t/60-second-timeout-for-http-server/1243/2
- Tigris pricing: https://www.tigrisdata.com/pricing/
- Tigris lifecycle rules: https://www.tigrisdata.com/docs/buckets/object-lifecycle-rules/
- Tigris bucket locations: https://www.tigrisdata.com/docs/buckets/locations/

Deno Deploy:

- Pricing: https://deno.com/deploy/pricing
- Runtime lifecycle and eviction: https://docs.deno.com/deploy/reference/runtime/
- Env vars and secrets: https://docs.deno.com/deploy/reference/env_vars_and_contexts/
- Migration from Classic (regions, shutdown date): https://docs.deno.com/deploy/migration_guide/

Google Cloud:

- Cloud Run WebSockets: https://docs.cloud.google.com/run/docs/triggering/websockets
- Cloud Run request timeout: https://docs.cloud.google.com/run/docs/configuring/request-timeout
- Cloud Run pricing: https://cloud.google.com/run/pricing
- IAP for Cloud Run: https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run
- Secret Manager pricing: https://docs.cloud.google.com/secret-manager/pricing
- Cloud Storage lifecycle: https://docs.cloud.google.com/storage/docs/lifecycle
- Cloud Storage pricing (always-free regions): https://cloud.google.com/storage/pricing

Vercel:

- WebSockets: https://vercel.com/docs/functions/websockets ;
  https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections
- Function limits: https://vercel.com/docs/functions/limitations
- Hobby plan: https://vercel.com/docs/plans/hobby
- Pro plan: https://vercel.com/docs/plans/pro-plan
- Regions: https://vercel.com/docs/regions
- Vercel Blob: https://vercel.com/docs/vercel-blob
- Deployment Protection: https://vercel.com/docs/deployment-protection

Hetzner:

- Cloud locations: https://www.hetzner.com/cloud/
- Cost-optimized plans (availability): https://www.hetzner.com/cloud/cost-optimized/
- Price adjustment 2026-06-15: https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/ ;
  https://www.hetzner.com/pressroom/standardization-and-price-adjustment-of-our-server-products/
- Primary IPs: https://docs.hetzner.com/cloud/servers/primary-ips/overview/
- Object Storage: https://docs.hetzner.com/storage/object-storage/overview/ ;
  https://www.hetzner.com/storage/object-storage/
- Object Storage lifecycle: https://docs.hetzner.com/storage/object-storage/howto-protect-objects/manage-lifecycle/
- Object Storage base price after April 2026 [search]: https://european-alternatives.eu/product/hetzner-object-storage

Tailscale:

- Funnel: https://tailscale.com/kb/1223/funnel
- Pricing: https://tailscale.com/pricing

GitHub:

- GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
