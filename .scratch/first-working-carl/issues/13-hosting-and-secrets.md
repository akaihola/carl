# Hosting and secrets

Type: grilling
Status: resolved
Blocked by: 05, 06, 16

## Question

Where is the first working version hosted (the page, and any server), how are provider API keys kept out of the page and the repo, who can reach it (only the owner's phone? a login?), and how are the normal and dev versions deployed?

## Answer

Settled with the owner in a grilling session (2026-09-26). The owner chose
to follow [akaihola/drum-transcribe](https://github.com/akaihola/drum-transcribe)'s
cloud setup (its `docs/operations.md`, `docs/recovery.md`,
`docs/loading-page-plan.md`, `docs/webapp.md` → Throttling), so its choices
are the defaults below. This overrides the Cloudflare Workers recommendation
from [Hosting a small backend](05-hosting-small-backend.md#answer); see
[ADR 0002](../../../docs/adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md).

1. **Host: one Scaleway Serverless Container** (fr-par) running a Python
   server (asyncio + a WebSocket library, `uv`), built from a slim image,
   **scaled to zero** when idle and **max scale 1**, so every connection of a
   session reaches the same instance. It serves both the page and the
   WebSocket. A Scaleway Instance was rejected: it can't scale to zero (about
   €3.50 a month always on).
2. **Address `faktat.vempai.men`**: a CNAME in the Cloudflare `vempai.men`
   zone, **proxied**, pointing at the container endpoint (zone SSL "Full";
   Scaleway keeps its own certificate for the domain).
3. **Loading page in front** (the owner's "launch counter"): a copy of
   drum-transcribe's Cloudflare Worker (`deploy/cloudflare/worker.js`, free
   plan, route `faktat.vempai.men/*`, fail open). A page load that the
   container doesn't answer within 2.5 s gets a "Starting up…" page with a
   seconds counter, which polls a cheap side-effect-free endpoint and
   reloads when the container is up. A second route,
   `faktat.vempai.men/api/*`, has no Worker, so the session WebSocket, the
   health poll and all API calls go straight through Cloudflare's proxy.
   Off switch: set the DNS record back to "DNS only".
4. **The 60-minute request limit** (Scaleway, see
   [Scaleway as Carl's host](16-scaleway-hosting.md#answer)) is met with a
   **planned handover**: at about 50 minutes the page opens a second
   WebSocket, moves the audio onto it and then closes the old one. Nothing is
   lost, and the server's speech-to-text stream stays open. Every other drop
   (Cloudflare or Scaleway restarts, network) uses the 2-minute reconnect
   grace period from
   [What runs in the browser and what runs on a server](06-browser-and-server-split.md#answer).
   Session state is saved to the bucket (`sessions/<id>/state.json`) as it
   changes, so a restart or scale-down resumes. **An early build step
   measures the real limit** with a 2-hour test connection through the proxy.
   The same test checks whether the container's CPU is throttled while no
   page is connected (drum-transcribe saw throttling between requests),
   because checks keep running during the grace period.
5. **Who can reach it: access passes.** The whole site sits behind a
   password gate: page, WebSocket, API and admin routes, with only the health
   endpoint and the loading page open. The owner can set **several access
   passes**, each a scrypt entry (`salt:hash`) in the `CARL_PASSWORDS` secret
   variable, made by a `hash-password` command that also generates four-word
   passphrases (~72 bits). A correct pass sets a stateless cookie,
   `HMAC(TOKEN_SECRET, salt of that entry)` (HttpOnly, Secure, SameSite=Lax,
   1 year), which the browser also sends on the WebSocket upgrade.
   Deleting an entry revokes that pass's cookies; rotating `TOKEN_SECRET`
   revokes all. A wrong pass waits 1 s; no lockout.
6. **Storage: one Scaleway Object Storage bucket** in fr-par, reached with a
   **scoped IAM-application key** (object storage only, with an expiry date),
   as in drum-transcribe. It holds everything that
   [Where the card archive, failure log and recording sessions are kept](11-storage-expiry-deletion.md#answer)
   put on the server:
   - `recordings/<id>/`, deleted by a 180-day lifecycle rule;
   - `corpus/<id>.md`, no expiry;
   - `sessions/<id>/state.json` for resuming;
   - `failures/`, deleted by a 30-day lifecycle rule;
   - `costs/`: per-session cost summaries and one month-to-date object,
     rewritten by the single instance, kept indefinitely.

   Local runs write under a `dev/` prefix in the same bucket.
7. **Secrets.**
   - All provider keys, the bucket key, `CARL_PASSWORDS` and `TOKEN_SECRET`
     are the container's **secret environment variables**. The whole map is
     set in one update, because Scaleway replaces all of it each time.
   - Locally they live in gitignored `.secrets.*` files at the repo root.
     Every one of them, plus the Scaleway and Cloudflare API credentials
     (`.secrets.cloudflare.env`, a Workers token limited to the zone), is
     copied into the owner's password manager.
   - A recovery doc lists them, as drum-transcribe's `recovery.md` does.
     `TOKEN_SECRET` can't be recreated without logging every browser out.
   - Nothing secret is in the page, the image or the repo.
   - **A hard monthly spend limit** is set in every provider dashboard that
     offers one, as a backstop while the budget warning is out of scope.
8. **Deploys: one cloud deploy only, by hand.** `docker build`, push to the
   Scaleway registry, `scw container redeploy`; the Worker with
   `npx wrangler deploy`. Never during a dinner, because a redeploy drops
   live sessions. Staging is the same server run locally, using the `dev/`
   prefix. Development mode is not a separate deploy; how a session is
   switched into recording is still open (see the map's fog).
9. **The per-deploy config file** (models, thresholds, price table, USD→€
   rate, blocklist) is committed and baked into the image. Changing it means
   a redeploy.
10. **The owner-only script** uses the bucket key directly for `list`,
    `fetch` and `delete`, and month totals are read from `costs/`, so no
    admin route is needed now.

## Comments

- Owner's steers from [What "done" means for the first working version](01-done-for-first-version.md#answer): see its answer.
- From [Where the card archive, failure log and recording sessions are kept](11-storage-expiry-deletion.md#answer): the host needs EU-only object storage with prefix lifecycle rules (180 days on `recordings/`, none on `corpus/`), no versioning, and a small store for the failure log with 30-day expiry. The owner reaches the bucket from their computer with an owner-only script.

- From [Metering running cost against the monthly budget](12-cost-metering.md#answer): the server store that holds the failure log also keeps per-session cost summaries and a month-to-date total indefinitely (no conversation content), and the per-deploy config file carries a price table and a fixed USD→€ rate.
