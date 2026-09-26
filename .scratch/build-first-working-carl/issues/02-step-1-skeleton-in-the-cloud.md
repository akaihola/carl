# Step 1: Skeleton in the cloud

Type: task
Status: open
Blocked by: 01

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
  - a note for the owner to copy each secret into their password manager and
    to set a hard monthly spend limit in every provider dashboard that offers
    one.
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

- [ ] pytest passes in GitHub Actions on push to `main`: the access-pass
      checks, the cookie, the prompt loader's placeholder check and the
      config loading, with no live provider calls.
- [ ] Deployed, and `faktat.vempai.men` opened on the phone behind an access
      pass, with the loading page seen on a cold start.
- [ ] The 2-hour connection test is run and its results are written under an
      `## Answer` heading here: the real cut, CPU throttling with no page
      connected, and the cold start time.
- [ ] If the handover looks unworkable, or the CPU is throttled while no page
      is connected, this is raised with the owner before step 2. The
      fallback is a Scaleway Instance running the same image
      ([ADR 0002](../../../docs/adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md)).
