# Step 1: Container, bucket and secrets

Type: task
Status: open
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

- [ ] The container runs the image and answers `/api/health` on its
      Scaleway endpoint, behind the access pass.
- [ ] The bucket exists with its three lifecycle rules and no versioning,
      and the scoped key can reach it.
- [ ] The operations and recovery docs are written.
