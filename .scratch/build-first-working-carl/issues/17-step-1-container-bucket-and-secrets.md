# Step 1: Container, bucket and secrets

Type: task
Status: resolved
Blocked by: 12, 13, 14, 15

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). The
[First working Carl spec](../../first-working-carl/spec.md) is the source of
truth: [Hosting](../../first-working-carl/spec.md#hosting),
[Secrets](../../first-working-carl/spec.md#secrets),
[Storage](../../first-working-carl/spec.md#storage) and
[Deploys and the config file](../../first-working-carl/spec.md#deploys-and-the-config-file).
drum-transcribe's `docs/operations.md` and `docs/recovery.md` are the model.
It needs the Scaleway credentials (`SCW_*`).

## What to build

- **A slim Dockerfile** with the server, the page, the config file and
  `prompts/`, and nothing secret.
- **One Scaleway Serverless Container** in fr-par, scaled to zero, max scale
  1, in its own registry and containers namespaces.
- **The bucket:** one Object Storage bucket in fr-par, no versioning, with
  lifecycle rules `recordings/` 180 days, `failures/` 30 days and `sessions/`
  1 day. Local runs write under `dev/`.
- **A scoped IAM-application key** that covers object storage only and has
  an expiry date.
- **The container's secret environment variables:** `CARL_PASSWORDS`,
  `TOKEN_SECRET` and the bucket key, always set together in one update,
  since Scaleway replaces the whole set. The provider keys join them with
  the steps that use them.
- **Gitignored `.secrets.*` files** at the repo root for the local copies.
- **Deploy commands:** `docker build`, push to the Scaleway registry,
  `scw container redeploy`, written down in an operations doc.
- **A recovery doc** listing every secret, as drum-transcribe's `recovery.md`
  does, with a note for the owner to copy each secret into their password
  manager, to buy provider credits in small prepaid batches with automatic
  top-up off, and to set a hard monthly spend limit in every provider
  dashboard that offers one at launch.

## Done when

- [x] The container runs the image and answers `/api/health` on its
      Scaleway endpoint, behind the access pass.
- [x] The bucket exists with its three lifecycle rules and no versioning,
      and the scoped key can reach it.
- [x] The operations and recovery docs are written.

## Comments

- 2026-09-27: Done, in the Scaleway project AI app prototypes (fr-par):
  - `deploy/Dockerfile` and `.dockerignore`: a two-stage build on
    `python:3.13-slim` from `mirror.gcr.io`, with the locked dependencies
    installed by uv, the config file and `prompts/`, running as `nobody`.
    193 MB. It fails closed without its secrets. A TLS-intercepting proxy's
    CA can be passed as the BuildKit secret `ca`, which never enters the
    image.
  - The registry namespace `carl`, with a first image,
    `rg.fr-par.scw.cloud/carl/carl:87f5d5d`.
  - The bucket `carl-faktat`: versioning never enabled, and lifecycle rules
    `recordings/` 180 days, `failures/` 30 days and `sessions/` 1 day, plus
    the same three under `dev/`, so local runs expire the same way.
  - The IAM application `carl-server` with the policy `carl-server-objects`
    (objects read, write and delete, and buckets read, in this project
    only; the project holds no other bucket) and an API key expiring on
    2027-09-27. Checked with the key: it puts, gets, lists and deletes
    objects, and is refused changing the lifecycle rules, turning on
    versioning and creating a bucket.
  - The containers namespace `carl`.
  - `deploy/deploy.sh` (build, push, `scw container container update` and
    `redeploy`) and `deploy/secrets.py` (the whole secret set in one
    update, refusing an incomplete one). Neither has run against the
    container yet, since it doesn't exist.
  - `docs/operations.md` and `docs/recovery.md`, with the owner's note on
    the password manager, prepaid credits and spend limits.
  - The production secrets are in gitignored files in the session that
    made them: `.secrets.carl.env` (`CARL_PASSWORDS` with one pass for the
    owner's phone, and `TOKEN_SECRET`), `.secrets.access-passes.txt` (the
    passphrase) and `.secrets.bucket.env` (the bucket key). The owner
    copies them into the password manager and the cloud environment's
    variables.
  - Not done: creating the container. Claude Code's auto-mode safety check
    refused `scw container container create`, so the session stopped
    before it and left the decision to the owner. The command is step 5
    of the first-time setup in `docs/operations.md`.
- 2026-09-27: The owner approved creating the container, and it is done:
  the container `carl` in the namespace `carl` (scaled to zero, max scale
  1, 1 GB and 560 mvCPU, timeout 3600 s), with all eight secrets set in
  one update by `deploy/secrets.py`: `CARL_PASSWORDS`, `TOKEN_SECRET`, the
  bucket key and the four provider keys. It answers `/api/health` on its
  Scaleway endpoint, and everything else there sits behind the access
  pass. `deploy/deploy.sh` has deployed each step since; the running image
  is `rg.fr-par.scw.cloud/carl/carl:558c6b7`.
