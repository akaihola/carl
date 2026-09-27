# Operations

How Carl runs, locally and in the cloud, and how it is deployed. It follows
[akaihola/drum-transcribe](https://github.com/akaihola/drum-transcribe)'s
cloud setup ([ADR 0002](adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md)).
The secrets are listed in [recovery.md](recovery.md).

## Running it locally

```sh
uv run pytest                                           # the tests, no network
uv run carl hash-password                               # a new access pass and its entry
uv run --env-file .secrets.carl.env --env-file .secrets.bucket.env \
  --env-file .secrets.providers.env carl serve         # http://localhost:8080
uv run carl owner list [--dev]                          # recording sessions in the bucket
uv run carl owner tail [<id>] -f [--context] [--dev]    # the decision model's calls as they happen
```

- The server refuses to start without `CARL_PASSWORDS` and `TOKEN_SECRET`,
  so a local run needs `.secrets.carl.env` (see [recovery.md](recovery.md)).
  A browser accepts the access-pass cookie on `http://localhost`, though it
  is marked Secure.
- Staging is this same server run locally. Local runs write under `dev/` in
  the bucket, where `carl owner … --dev` finds them. Without
  `.secrets.bucket.env` they write to the gitignored folder `.carl-store/`
  instead. `.secrets.providers.env` holds the provider keys, such as
  `SONIOX_API_KEY`, which the server needs to start.
- Reverse geocoding uses the public Nominatim server. `CARL_NOMINATIM_URL`
  points Carl at another one, as Nominatim's usage policy asks for heavier
  use.
- `carl dev-send <file>` sends an audio file to a local server as if from
  the microphone.
- `carl owner tail` prints a session's decision and settle calls from its
  event log: the utterance, what Carl made of the answer, the answer's
  probabilities, and the call's time, tokens and cost. `-f` keeps polling
  the bucket for new log parts, which the server writes about every 10 s,
  so calls show up 5–15 s after they are made. `--context` adds the rest of
  the prompt's fields. Without an id it picks the newest session.
- `carl serve --config … --prompts …` picks another config file or prompts
  folder.

## The cloud

Everything is in the Scaleway project **AI app prototypes**, region fr-par,
and the Cloudflare zone **vempai.men**.

| What | Name | Notes |
| --- | --- | --- |
| Registry namespace | `carl` | Private. Images are `rg.fr-par.scw.cloud/carl/carl:<commit>` |
| Containers namespace | `carl` | |
| Container | `carl` | Scaled to zero, max scale 1, 1 GB and 560 mvCPU, timeout 3600 s (Scaleway's most), port 8080, HTTPS only, public (the access pass guards it) |
| Bucket | `carl-faktat` | No versioning. Lifecycle rules: `recordings/` 180 days, `failures/` 30 days, `sessions/` 1 day, and the same three under `dev/` |
| IAM application | `carl-server` | Policy `carl-server-objects`: read, write and delete objects and read buckets, in this project only. Its API key expires on 2027-09-27 |
| Address | `faktat.vempai.men` | CNAME to the container's endpoint, proxied, zone SSL "Full". Scaleway keeps its own certificate for the domain |
| Worker | `faktat-front` | On `faktat.vempai.men/*`, failing open: answers requests without an access-pass cookie itself, and shows the loading page. `faktat.vempai.men/api/ws` has no Worker |

The container's plain environment variables are `S3_ENDPOINT`,
`S3_REGION` and `S3_BUCKET`. Its secret ones are set only with
`deploy/secrets.py` (below).

The container's own endpoint is
`https://carl2255fb5c-carl.functions.fnc.fr-par.scw.cloud`. It works too,
behind the same access pass, but without the Worker, so every request to it
reaches the container.

## Deploying

Never during a dinner: a redeploy drops live sessions. The config file and
`prompts/` are baked into the image, so changing either means a deploy.

```sh
deploy/deploy.sh
```

It refuses to run with uncommitted changes, since the image is tagged with
the commit, and then:

1. `docker build -f deploy/Dockerfile` (set `DOCKER=podman` for podman);
2. pushes the image to `rg.fr-par.scw.cloud/carl`;
3. `scw container container update <id> image=…`, which redeploys the
   container, or `scw container container redeploy <id>` when the image is
   the same.

It needs `docker login rg.fr-par.scw.cloud/carl -u nologin
--password-stdin` (the password is the Scaleway secret key) and `scw` with
the owner's Scaleway API key. Then check
`https://carl2255fb5c-carl.functions.fnc.fr-par.scw.cloud/api/health`: at
`faktat.vempai.men` it answers only with the access-pass cookie.

The Worker is deployed on its own, only when `deploy/cloudflare/` or
`src/carl/pass.html` (the pass form, which it bundles) changes:

```sh
cd deploy/cloudflare && set -a && . ../../.secrets.cloudflare.env && set +a && npx wrangler@4 deploy
```

Afterwards check that the main route still fails open (below).

### Secrets

Scaleway replaces a container's whole set of secret variables on every
update, so a secret left out is deleted and the server then won't start.
Change them only with:

```sh
python3 deploy/secrets.py --check    # is every secret at hand?
python3 deploy/secrets.py            # set them all in one update; the container redeploys
```

It reads the gitignored `.secrets.*` files at the repo root (a variable in
the environment wins) and refuses to send an incomplete set. When a build
step adds a provider, add its key to `SECRETS` in the script and to
[recovery.md](recovery.md).

### From a Claude Code cloud session

The owner's cloud environment has the `SCW_*` and `CLOUDFLARE_*` variables.
What it needs, found on 2026-09-27:

- Start Docker's daemon with `dockerd` in the background.
- Docker Hub answers anonymous pulls with 429, so the Dockerfile's base
  image comes from Google's mirror, `mirror.gcr.io`.
- TLS goes through a proxy that re-signs it, so builds need its CA:
  `CA_BUNDLE=/root/.ccr/ca-bundle.crt deploy/deploy.sh`. The CA reaches the
  build only as a BuildKit secret and never enters the image.
- `scw` can't be downloaded from GitHub there. Take it from its image:
  `docker create mirror.gcr.io/scaleway/cli:latest`, then `docker cp
  <id>:/usr/bin/scw ~/.local/bin/scw`.
- aiohttp takes a `wss://` connection's proxy from `WSS_PROXY`, so a local
  server there reaches Soniox only with `WSS_PROXY=$HTTPS_PROXY` set.
- The secrets files don't survive the session. The owner keeps them in the
  password manager and in the environment's variables.

## First-time setup

What was run on 2026-09-27, in order, for rebuilding it. `$NS` is the
containers namespace's id (`scw container namespace list name=carl -o
template='{{ .ID }}'`).

1. Done: `scw registry namespace create name=carl is-public=false`.
2. Done: the bucket `carl-faktat` with its lifecycle rules, through the S3
   API with the owner's key.
3. Done: `scw iam application create name=carl-server`, the policy
   `carl-server-objects` (`ObjectStorageObjectsRead`,
   `ObjectStorageObjectsWrite`, `ObjectStorageObjectsDelete`,
   `ObjectStorageBucketsRead` on this project), and
   `scw iam api-key create application-id=… expires-at=2027-09-27T00:00:00Z`.
   The key is in `.secrets.bucket.env`.
4. Done: `scw container namespace create name=carl`.
5. The container.

   ```sh
   scw container container create namespace-id=$NS name=carl \
     image=rg.fr-par.scw.cloud/carl/carl:<commit> \
     min-scale=0 max-scale=1 memory-limit-bytes=1GB mvcpu-limit=560 timeout=3600s \
     privacy=public protocol=http1 port=8080 https-connections-only=true \
     environment-variables.S3_ENDPOINT=https://s3.fr-par.scw.cloud \
     environment-variables.S3_REGION=fr-par environment-variables.S3_BUCKET=carl-faktat
   python3 deploy/secrets.py
   ```

   The first deploy fails, as it should, until `deploy/secrets.py` has set
   the secrets: the server refuses to start without its access passes.
   Then `/api/health` answers on the container's own endpoint
   (`scw container container list namespace-id=$NS -o template='{{ .PublicEndpoint }}'`),
   and every other path asks for the access pass.
6. The address. In Cloudflare, a CNAME `faktat` to the container's
   endpoint, **DNS only** at first. Then bind the domain on Scaleway
   (`scw container domain create container-id=… hostname=faktat.vempai.men`)
   and wait until it is ready (about a minute), since Scaleway fetches its
   certificate over plain DNS. Then switch the record to **proxied**. The zone's SSL mode is
   already "Full" (checked on 2026-09-27), as drum-transcribe's `plokkaus`
   and `dallape` need it.
7. The Worker. `npx wrangler@4 deploy` from `deploy/cloudflare/`,
   then through the Cloudflare API:
   - `POST /zones/<zone>/workers/routes` with
     `{"pattern": "faktat.vempai.men/api/ws"}` and no `script`: the more
     specific pattern wins, so the WebSocket skips the Worker. A pattern
     without `*` matches only that path, whatever the query string;
   - set `request_limit_fail_open: true` on the `faktat.vempai.men/*`
     route, so requests over the free plan's daily limit skip the Worker
     instead of failing.

## The Worker

- **Scanners never reach the container.** They probe `faktat.vempai.men`
  every 10–30 minutes, and each request that reached the container would
  wake it and keep it up for about 15 minutes. So the Worker answers every
  request without an access-pass cookie itself, as Carl's gate would: the
  pass form (401) for a GET outside `/api/`, and a 401 "An access pass is
  needed." for anything else, `/api/health` included. Only the pass form's
  own `POST /api/unlock`, requests with the cookie and
  `/.well-known/acme-challenge/*` (Scaleway renewing its certificate for the
  domain) go through. The Worker only looks for the cookie; Carl's gate
  checks it.
- The pass form is `src/carl/pass.html`, which the server serves too and
  the Worker bundles, so a change to it needs the Worker deployed as well.
- **The loading page.** The Worker answers a GET page load that the
  container hasn't answered within 2.5 s with "Starting up…" and a seconds
  counter (status 503, `Cache-Control: no-store`). The original request
  carries on and keeps waking the container. The page polls `/api/health`
  every 2 s and reloads once it answers. Only page loads
  (`Sec-Fetch-Mode: navigate`) can get it; everything else with the cookie
  passes through untouched. The pass form's POST gets no loading page: it
  just waits for the container.
- Only `/api/ws` skips the Worker, so the WebSocket doesn't count against
  the free plan's 100,000 Worker requests a day. The health poll does, a
  few requests per cold start.
- **Off switch:** set the `faktat` DNS record back to "DNS only". The site
  then works as before, without the Worker, and scanners wake the
  container again.
- Cloudflare gives up on an origin that hasn't answered in 100 s (error
  524). The health poll just retries.

## Logs

`scw container container logs <id>` shows the container's output. At
startup the server logs its commit, the config's version and each prompt's
version, then one line per page connecting and leaving.

The same logs are in the project's Cockpit, in the data source "Scaleway
Logs", and the Scaleway secret key reads them through its Loki API (the
data source's URL comes from
`GET /cockpit/v1/regions/fr-par/data-sources?project_id=…`):

```sh
curl -sG -H "X-Auth-Token: $SCW_SECRET_KEY" \
  https://7e80bd3c-d744-4807-acfb-405a598cc91f.logs.cockpit.fr-par.scw.cloud/loki/api/v1/query_range \
  --data-urlencode 'query={resource_name="carl2255fb5c-carl"} |= "aiohttp.access"' \
  --data-urlencode "start=$(date -d '-1 day' +%s)000000000" --data-urlencode limit=5000
```

Each request's line is aiohttp's usual one (the address is always
Scaleway's proxy, 127.0.0.1) with how the request came at the end:

- `cf-worker=vempai.men`: the Worker passed it on;
- a `cf-ray=` but `cf-worker=-`: through Cloudflare without the Worker,
  as on `/api/ws`;
- `cf-ray=-`: straight to the container's own address, which the Worker
  can't stop. `|= "cf-ray=-"` in the query shows only these.

## Things to know

- Cloudflare stores responses with cacheable extensions (`.js`, `.css`,
  `.woff2`) in its edge cache unless told not to, and its 4-hour browser
  cache setting overrides `no-cache`. So everything behind the gate is sent
  with `Cache-Control: private, no-cache, no-transform`: `private` keeps it
  out of Cloudflare's cache, so the gate is asked every time, and
  `no-transform` stops Cloudflare injecting its analytics beacon, which the
  page's CSP would block anyway.

- Scaleway ends every request after exactly 60 minutes, a WebSocket
  included: the cut counts from the request's start, not from idleness.
  The page hands its session over to a new WebSocket at 50 minutes, before
  the cut. Measured in step 1's 2-hour connection test
  ([ticket 02](../.scratch/build-first-working-carl/issues/02-step-1-skeleton-in-the-cloud.md#answer)),
  which also found the CPU keeps its pace while no page is connected.
- A cold start takes 5–10 s from the first request until `/api/health`
  answers: 4–7 s is Scaleway starting the instance, and about 2.4 s is
  Carl's own start. The Worker shows "Starting up…" for page loads that
  wait longer than 2.5 s. The first time a phone enters its access pass,
  the pass form's POST waits out the cold start instead.
- The container scales to zero after about 15 minutes without a request.
  An open WebSocket counts as a request, so it keeps the container up.
  Requests without an access-pass cookie don't reach it (the Worker answers
  them), so scanners don't.
- On a redeploy or scale-down the server closes every WebSocket with code
  1001, so pages reconnect at once.
