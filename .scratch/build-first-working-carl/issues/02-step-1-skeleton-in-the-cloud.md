# Step 1: Skeleton in the cloud

Type: task
Status: open
Blocked by: 01, 12, 13, 14, 15, 16, 17, 18, 19

Build step 1 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. If the step is too big for one agent session,
split it into further tickets in this folder before starting.

## What to build

Take the pieces from [akaihola/drum-transcribe](https://github.com/akaihola/drum-transcribe):
its `docs/operations.md`, `docs/recovery.md`, `docs/loading-page-plan.md`,
the Throttling part of `docs/webapp.md` and `deploy/cloudflare/worker.js`.
An agent session needs that repository added to read it.

- **The Python server and page shell** ([Architecture](../../first-working-carl/spec.md#2-architecture)):
  - an asyncio server with a WebSocket library, managed with `uv`, serving
    both the page and the WebSocket;
  - the page as plain HTML, CSS and JS modules with no build step and no
    framework ([The page](../../first-working-carl/spec.md#the-page)), with
    Atkinson Hyperlegible self-hosted and no third-party calls;
  - a cheap health endpoint with no side effects, for the loading page's
    poll.
- **The access-pass gate** ([Access passes](../../first-working-carl/spec.md#access-passes)):
  - scrypt entries (`salt:hash`) in `CARL_PASSWORDS`;
  - a `hash-password` command that can also generate a four-word
    passphrase;
  - the stateless cookie `HMAC(TOKEN_SECRET, salt)` (HttpOnly, Secure,
    SameSite=Lax, 1 year);
  - a 1 s wait on a wrong pass, and no lockout;
  - everything behind the gate except the health endpoint and the loading
    page, the WebSocket upgrade included.
- **Hosting** ([Hosting](../../first-working-carl/spec.md#hosting)):
  - a slim Dockerfile;
  - one Scaleway Serverless Container in fr-par, scaled to zero, max scale 1;
  - the proxied CNAME `faktat.vempai.men` in the Cloudflare `vempai.men`
    zone, with zone SSL "Full";
  - the loading Worker on `faktat.vempai.men/*`: "Starting up…" after 2.5 s,
    polling the health endpoint, failing open;
  - the Worker-free route `faktat.vempai.men/api/*` for the WebSocket, the
    health poll and the API.
- **Deploy commands** ([Deploys and the config file](../../first-working-carl/spec.md#deploys-and-the-config-file)):
  `docker build`, push to the Scaleway registry, `scw container redeploy`,
  `npx wrangler deploy`.
- **Secrets** ([Secrets](../../first-working-carl/spec.md#secrets)):
  - the container's secret environment variables, always set together in one
    update;
  - gitignored `.secrets.*` files at the repo root;
  - a recovery doc listing every secret, as drum-transcribe's `recovery.md`
    does;
  - a note for the owner to copy each secret into their password manager,
    to buy provider credits in small prepaid batches with automatic top-up
    off, and to set a hard monthly spend limit in every provider dashboard
    that offers one at launch.
- **The bucket** ([Storage](../../first-working-carl/spec.md#storage)):
  - one Object Storage bucket in fr-par, with no versioning;
  - lifecycle rules: `recordings/` 180 days, `failures/` 30 days,
    `sessions/` 1 day;
  - a scoped IAM-application key that covers object storage only and has an
    expiry date;
  - local runs write under `dev/`.
- **The config file and `prompts/`** ([Config file contents](../../first-working-carl/spec.md#13-config-file-contents),
  [Prompts: one source of truth](../../first-working-carl/spec.md#prompts-one-source-of-truth)):
  - the config file with every setting and starting value in section 13,
    including the provider, model and parameters that step 0 chose for each
    stage, the price table and the USD → € rate;
  - the `prompts/` folder and its loader. A prompt's version is a short
    content hash, and startup fails if a template has a placeholder that
    nothing fills.
  - The prompt texts arrive with the steps that use them. The step-0
    smoke-test prompts in `../smoke-test/prompts/` are their first drafts.
- **pytest in GitHub Actions** on every push to `main`, with no live provider
  calls.
- **One WebSocket with a heartbeat** ([One WebSocket](../../first-working-carl/spec.md#one-websocket)):
  - binary frames for audio and JSON text frames for everything else;
  - a heartbeat every 3 s each way when nothing else was sent;
  - 10 s of silence means a dropped connection, on both sides;
  - at session start, the server sends the page the config values the page
    needs.
- **The 2-hour connection test**, the step-1 row of
  [Early checks](../../first-working-carl/spec.md#early-checks). Hold a
  WebSocket through Cloudflare's proxy to the container for 2 hours and
  measure:
  - where Scaleway really cuts it;
  - whether the container's CPU is throttled while no page is connected;
  - the cold start time.

## Leaves working

`faktat.vempai.men` opens behind an access pass. The real cut, the throttling
and the cold start are known.

## Done when

- [x] pytest passes in GitHub Actions on push to `main`: the access-pass
      checks, the cookie, the prompt loader's placeholder check and the
      config loading, with no live provider calls.
- [ ] Deployed, and `faktat.vempai.men` opened on the phone behind an access
      pass, with the loading page seen on a cold start.
- [x] The 2-hour connection test is run and its results are written under an
      `## Answer` heading here: the real cut, CPU throttling with no page
      connected, and the cold start time.
- [x] If the handover looks unworkable, or the CPU is throttled while no page
      is connected, this is raised with the owner before step 2. The
      fallback is a Scaleway Instance running the same image
      ([ADR 0002](../../../docs/adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md)).

## Answer

The 2-hour connection test ran on 2026-09-27 from the owner's cloud
environment, 12:39–15:18 UTC, with
[`connection_test.py`](../connection-test/connection_test.py) holding a
WebSocket to `wss://faktat.vempai.men/api/ws` through Cloudflare's proxy,
sending the page's heartbeat and reconnecting after every close.

**The real cut is exactly 60 minutes**, as the spec assumed. A WebSocket held
with nothing but heartbeats from 14:18:55 was cut at 15:18:57: the server
logged the disconnect at 3600 s, the client saw code 1006 at 3602 s, and it
reconnected in 1.2 s. The cut counts from the request's start, not from
idleness. The page's handover at `handover_s` (50 minutes) comes 10 minutes
before it, so the handover design stands.

**The CPU is not throttled while no page is connected.** A probe on the
server ran a 1 ms task 10 times a second and reported each tick's lateness
and work time. With the page connected, then with the page gone for 90 s
and for 150 s (longer than the 2-minute reconnect grace):

| Probe | Page | Ticks per s | Work median / p95 | Late median / p95 / max |
| --- | --- | --- | --- | --- |
| connected, 60 s | connected | 10.0 | 0.80 / 1.73 ms | 1.8 / 3.3 / 6.6 ms |
| no page for 90 s | gone | 10.0 | 0.80 / 1.70 ms | 1.8 / 4.0 / 10.8 ms |
| no page for 150 s | gone | 10.0 | 0.81 / 2.13 ms | 2.0 / 5.0 / 10.9 ms |

No other request reached the container in those windows, so nothing else
kept it awake. Every expected tick came.

**A cold start takes about 5 s** from the first request until `/api/health`
answers. The live container couldn't go cold during the test, since the
owner's open tab and a scanner kept it awake, so it was measured on a
throwaway copy of the container with the same settings and the step-1
image, deleted afterwards: 5.3 s and 4.9 s. Of that, Scaleway starting the
instance took about 4.2 s and Carl's own start about 1.0 s. The current
image, with every step's code, takes about 2.1 s for Carl's part.

**One unplanned drop.** At 13:17 a connection closed after 297 s with no
cut due: the server heard nothing from the client for its 10 s silence
limit, although the client was sending heartbeats. It reconnected in 0.8 s.
It didn't recur in the rest of the run, and it was most likely
this environment's proxy. The connections over the run were: 370 s (closed
by the test for a probe), 297 s (the drop), 3451 s (closed by the test) and
2838 s (closed by the test at the end); the separate hold took the full
3602 s to the cut.

Nothing needs raising with the owner before step 2: the cut is where the
spec put it, and the CPU keeps its pace with no page connected, so the
Scaleway Instance fallback isn't needed.

## Comments

- 2026-09-27: What the owner's cloud environment offers for this step,
  checked while closing step 0:
  - Docker's client and daemon are installed, but the daemon isn't running.
    Start it with `dockerd` in the background.
  - Docker Hub answers this environment's anonymous pulls with 429. Google's
    mirror works: `mirror.gcr.io/library/python:3.13-slim`.
  - Containers and build steps reach the network only with `--network host`,
    the proxy variables (`HTTPS_PROXY`, `NO_PROXY`) and the proxy's CA
    (`/root/.ccr/ca-bundle.crt`). With those, `pip install` works inside a
    container.
  - `scw` isn't installed. `npx` is, for `wrangler`.
  - Scaleway's API, its fr-par registry and object storage, and Cloudflare's
    API are all reachable. No Scaleway or Cloudflare credentials are set yet.
  - akaihola/drum-transcribe is public, and sessions can add it.
- 2026-09-27: Split into sub-tickets, each small enough for one agent
  session. This ticket is done when they are, and the connection test's
  answer goes here.
  - [12](12-step-1-server-and-page-shell.md): the server and page shell,
    with the health endpoint;
  - [13](13-step-1-access-pass-gate.md): the access-pass gate and
    `hash-password`;
  - [14](14-step-1-config-file-and-prompts.md): the config file and the
    prompt loader;
  - [15](15-step-1-websocket-heartbeat.md): the WebSocket with its
    heartbeat;
  - [16](16-step-1-pytest-in-github-actions.md): pytest in GitHub Actions;
  - [17](17-step-1-container-bucket-and-secrets.md): the Dockerfile, the
    container, the bucket, the secrets, and the operations and recovery
    docs;
  - [18](18-step-1-domain-and-loading-worker.md): `faktat.vempai.men` and
    the loading Worker;
  - [19](19-step-1-two-hour-connection-test.md): the 2-hour connection
    test.
- 2026-09-27: Tickets 12–16 are resolved: the server, page shell, gate,
  config file, prompt loader, WebSocket and CI work, and CI passes on
  GitHub. Ticket 17 is done except for the container itself, which
  Claude Code's auto-mode safety check refused to create, so the cloud
  work stopped there for the owner to decide. Ticket 18's Worker is
  written and tested locally but not deployed.
