# Scaleway as Carl's backend host

Follow-up to [hosting-small-backend.md](hosting-small-backend.md), compiled
2026-09-25. It answers one question: **how does Scaleway compare with
Cloudflare Workers + Durable Objects + R2 for Carl's small backend**, and could
a Scaleway GPU run a self-hosted speech-to-text model (NVIDIA Parakeet v3)
more sensibly than a Vast.ai rental? The Cloudflare figures are the ones
verified in the earlier file and are not repeated in full here.

## How this was researched, and how far to trust it

- Claims marked **[verified]** were read on 2026-09-25 from Scaleway's own
  documentation (the Markdown versions listed in its `llms.txt`) or pricing
  pages, from the Hugging Face model card NVIDIA publishes, or from Vast.ai's
  documentation, all listed under *Sources*.
- **[api]** marks Vast.ai marketplace prices read on 2026-09-25 from Vast.ai's
  public offer-search API (verified, on-demand, currently unrented single-GPU
  offers). They move daily; treat them as a snapshot.
- **[inference]** marks a conclusion I drew from the documents that no
  document states directly. Test these before relying on them.
- Scaleway prices are list prices in EUR for the Paris region, excluding VAT.
  Vast.ai prices are in USD.

The requirements are the ones from the earlier file: a phone-to-server
connection and a server-to-speech-to-text connection each open for up to about
2 hours; API keys kept off the page; recordings kept 6 months and then deleted
automatically; low fixed cost and little operations work; owner-only access;
EU location preferred.

## Summary

1. **Scaleway's serverless products fail the 2-hour test the same way Cloud
   Run does.** Serverless Containers and Serverless Functions both cap an HTTP
   request at **60 minutes** ("10 seconds to 60 minutes"), and Containers
   accept WebSockets as one of the request types they handle. A 2-hour session
   would be cut at least once. (Serverless Jobs run up to 24 hours but are
   batch jobs, not HTTP endpoints.)
2. **A small Scaleway Instance passes it, as any VM would**, with no platform
   duration limit. STARDUST1-S (1 vCPU, 1 GB) is listed at **about €0.43 a
   month** and DEV1-S (2 vCPU, 2 GB) at **about €6.55**, plus a public IPv4
   (about €2.90–3.65 a month) and a disk. That puts it in the Hetzner VPS
   category: cheap, EU, and all the operations work is the owner's.
3. **Object Storage meets the 6-month deletion rule.** Lifecycle rules can
   "automatically expire and delete the current version of your objects after
   the specified number of days". Rules run daily at midnight UTC and can take
   up to 24 hours more, as on R2. 30 GB costs **about €0.48 a month**
   (Standard Multi-AZ) or €0.24 (One Zone).
4. **Secrets and EU location are fine; owner-only access is weaker than
   Cloudflare's.** Secret environment variables can't be read back in the
   console, and every Scaleway region (Paris, Amsterdam, Warsaw) is in the EU,
   run by a French company. But there is no Cloudflare Access equivalent: a
   "private" container needs an IAM API key in an `X-Auth-Token` header, which
   a browser WebSocket cannot send and which would put a key in the page
   anyway, so Carl would need its own login.
5. **Cloudflare still fits Carl better.** It has no hard limit on connection
   length, a built-in single-owner login, EU jurisdiction for state and
   recordings, and $0–5 a month. Scaleway's edge is an all-EU, EU-owned
   provider with ordinary containers and VMs (any language, any SDK); to get
   long connections there you have to run an Instance.
6. **A Scaleway GPU can run Parakeet v3, but it is a costly way to do it at
   Carl's scale.** The cheapest GPU, L4-1-24G, is **€0.79 an hour**, billed
   per minute while powered on: about **€1.60 per 2-hour session**, or
   about €575 a month if left on. There is no serverless GPU option, so the
   instance must be started before a session and stopped afterwards. Vast.ai
   rents comparable GPUs for **$0.16–0.54 an hour**, EU hosts included [api],
   but on a marketplace where "hosts can technically access files on their
   machines" and a stopped GPU can be rented away. Carl's audio is private
   conversation, so Scaleway is the more defensible choice of the two.
   Neither answers Parakeet's own gaps: it has **no diarization** and only
   **chunked, not true, streaming**.

## Comparison with Cloudflare at a glance

| Requirement | Cloudflare Workers + DO + R2 | Scaleway Serverless Containers | Scaleway Instance |
|---|---|---|---|
| 2-hour connection | No hard limit; dropped on deploy and on Cloudflare restarts | **60 min max** request timeout | No platform limit |
| Idle behaviour | Idle WebSockets closed after an unpublished period | Scales to zero after 15 min with no requests | None |
| Language / SDKs | JS/TS (or Wasm) in the Workers runtime | Any container image | Anything |
| Fixed cost / month | $0 (free) or $5 (Workers Paid) | ~€0 inside the free tier | ~€3.50 (Stardust + IPv4) to ~€10 (DEV1-S + IPv4), plus disk |
| EU location | DO and R2 `eu` jurisdiction; Worker runs at the nearest edge | fr-par, nl-ams or pl-waw | Paris, Amsterdam or Warsaw zones |
| Storage with expiry | R2 lifecycle rules, ~$0.30 for 30 GB | Object Storage lifecycle rules, ~€0.48 for 30 GB | Same Object Storage, or local disk and a deletion job |
| Secrets | `wrangler secret`, hidden after set | Secret environment variables, hidden after set; Secret Manager | Owner's own (env file etc.) or Secret Manager |
| Owner-only access | Cloudflare Access, free | Private containers need an IAM key header (not usable from a browser WebSocket [inference]) | Owner's own |
| Static page | Free static assets, same hostname | Object Storage bucket website; Edge Services from €0.99/month for a custom domain with TLS | Owner's own web server |

## Serverless Containers and Functions [verified]

**Connection limits.**

- Containers: "HTTP request duration (timeout): 10 seconds to 60 minutes",
  with the footnote "Use Serverless Jobs for tasks up to 24h." Functions have
  the same 10 s to 60 min range.
- An application fits Serverless Containers if "it must handle requests
  delivered via HTTP, HTTP/2, WebSockets, or gRPC." Protocols: "HTTP/1.1 and
  HTTP/2 connections. HTTP/1.0 is not supported." Functions list only
  HTTP/1.1 and HTTP/2 ("Other protocols are not supported").
- The docs don't say explicitly that a WebSocket counts against the request
  timeout. A WebSocket starts as an HTTP request, so I assume it is cut at
  the configured timeout, at most 60 minutes [inference]. Either way the docs
  give no way to go past 60 minutes.
- Scaling: with min-scale 0, "all instances of your resource will be
  terminated after 15 minutes of inactivity"; scale-down to 1 happens after
  30 s with no requests. Redeploying "does not entail downtime. Instances are
  gradually replaced", but the docs don't say what happens to open
  connections on the replaced instances.
- Functions handle one request at a time per instance (concurrency 1).
  Containers take up to 80 concurrent requests per instance.
- Size: 70 to 6,000 mvCPU and 128 to 12,228 MB per container.
- No GPU is offered on Serverless Containers; GPUs are only on GPU Instances
  and Kubernetes node pools, as far as the docs index shows.

**Pricing.** Containers: €0.000002 per GB-s after **400,000 GB-s free** and
€0.00001 per vCPU-s after **200,000 vCPU-s free**, per account per month.
Ingress and egress are free. A 2-hour session on 0.25 vCPU and 512 MB uses
1,800 vCPU-s and 3,600 GB-s, so a few sessions a month cost nothing. Keeping
one such instance warm all month (min-scale 1) would be about **€6.40 a
month** after the free tier. Functions: €0.000005 per GB-s after 400,000
free, plus €0.15 per million requests after 1 million free.

**Secrets.** "Secret environment variables for sensitive data"; "You will not
be able to read the value in the console once submitted." Setting one
redeploys the container. Up to 200 per container and namespace.

**Access control.** A container can be set to Private: "Unauthenticated calls
will be rejected". It is then called with `X-Auth-Token: <API_SECRET_KEY>`,
the secret of an IAM API key whose application holds the
`ContainersPrivateAccess` permission set; calls without the header get 403.
The browser `WebSocket` constructor takes only a URL and subprotocols, so the
phone's page can't add that header [inference], and the key would have to
live in the page. So Carl would leave the container public and check a login
of its own.

**Custom domain.** Supported with a Scaleway-issued TLS certificate once the
CNAME points at the container endpoint.

## Instances [verified]

**Shape.** An ordinary VM, as with Hetzner.

**Connection limits.** None from the platform.

**Pricing (PAR-1).** STARDUST1-S, 1 vCPU and 1 GB, €0.0006 an hour (~€0.43 a
month); DEV1-S, 2 vCPU and 2 GB, €0.00898 an hour (~€6.55 a month); PLAY2-PICO,
1 vCPU and 2 GB, ~€10.42 a month. "List prices include egress and IPv6
addresses. Storage (local, block) and attached public IPv4 addresses are
excluded." CPU Instances are billed per hour of uptime. The Instances FAQ
says a flexible IPv4 costs €0.004 an hour (~€2.90 a month), while the network
pricing page lists €0.005 an hour (~€3.65) for an additional Instance IP.
Block Storage 5K is €0.000130 per GB-hour (~€0.95 a month for 10 GB). IPs and
volumes are billed "regardless of whether the Instance is powered off".

**Operations.** The same as any VPS: OS updates, TLS, a process supervisor,
firewall, secrets on disk, and a login of Carl's own or Cloudflare Access in
front.

## Object Storage [verified]

**Lifecycle deletion.** Rules can "automatically expire and delete the
current version of your objects after the specified number of days" (and
non-current versions, and incomplete multipart uploads), for the whole bucket
or filtered by prefix or tag. "The expiration and transition rules are
implemented every day at midnight UTC, but the actual action might take
between one minute and twenty-four hours after implementation." Set up in
the console or through the S3-compatible API.

**Pricing (Paris).** Standard Multi-AZ €0.01606 per GB-month, Standard One
Zone €0.00803, Glacier €0.00254. Requests and ingress are included; 75 GB of
egress a month is free. New accounts can activate a 90-day trial with 750 GB
free. At 30 GB: **~€0.48 a month** (Multi-AZ) or ~€0.24 (One Zone).
Transitions to cheaper classes need 30 days (One Zone) or 90 days (Glacier)
first, and Glacier objects must be restored before reading, so for a 6-month
store they save little.

**Location.** Standard Multi-AZ is in `fr-par`, `nl-ams` and `pl-waw`; One
Zone in all regions. A deleted bucket "is deleted instantly" through the API.

**Static page hosting.** "The Bucket Website feature allows you to host
static websites using Scaleway Object Storage"; enabling it makes "all
objects in the bucket ... publicly visible" by default. The site gets a
Scaleway website URL. For a custom domain with a TLS certificate, Edge
Services' Starter plan is **€0.99 a month** (100 GB of cache egress,
Let's Encrypt free). The page needs HTTPS for microphone access, so plain
HTTP on a CNAME is not enough.

## Secret Manager [verified]

A separate product, if Carl's backend should fetch keys at run time instead of
from environment variables: €0.04 per secret version a month and €0.03 per
10,000 access requests. Secrets are encrypted with AES-256 envelope
encryption, "replicated in different zones within a region", and available in
PAR, WAW and AMS. Access is by IAM policy. For a handful of provider keys
that is a few tens of cents a month.

## GPUs for self-hosted speech-to-text

**Parakeet v3 [verified].** `nvidia/parakeet-tdt-0.6b-v3` supports 25
European languages **including Finnish and English**, under CC-BY-4.0. It
needs "at least 2GB RAM for model to load" and was tested on A10, A100, A30,
H100, L4, L40, T4 and V100. It handles up to 24 minutes of audio with full
attention or 3 hours with local attention. The model card's streaming script
does **chunked inference** (e.g. `chunk_secs=2`), not true streaming, and
**diarization is not part of the model**; NVIDIA offers a separate
diarization model. So "self-hosted Parakeet" means building the streaming and
speaker-labelling layer that hosted vendors provide
(see [streaming-speech-to-text.md](streaming-speech-to-text.md)).

**Scaleway GPU Instances [verified].**

- Cheapest: **L4-1-24G** (1× L4 24 GB, 8 vCPU, 48 GB RAM) at **€0.79 an
  hour**, ~€575 a month if always on, in PAR-1. L40S (48 GB) and H100 are in
  PAR-2; their prices were not shown for PAR-1.
- "GPU Instances: Billed per minute of uptime (including startup and standby
  time)." Standby "is charged as a running Instance"; to stop paying, power
  off, and the IP and volumes are still billed.
- No serverless or scale-to-zero GPU. Carl would have to start the instance
  before a session, wait for it to boot and load the model, and stop it
  afterwards [inference]. A 2-hour session plus about 10 minutes of start-up
  is about **€1.75**; four sessions a month is **about €7** plus a disk and IP.
- EU-only, Scaleway's own data centres.

**Vast.ai [verified docs, api prices].**

- A marketplace: "Prices are set by the market, not by Vast", billed per
  second while running. Storage is "billed continuously while your instance
  exists, regardless of running state".
- 2026-09-25 snapshot, single GPU, verified hosts, on-demand, cheapest to
  median $/hour [api]: RTX 3090 **0.16–0.24**, L4 **0.27–0.32**, RTX 4090
  **0.39–0.54**, RTX 5090 0.41–0.72, RTX A4000 0.08–0.11. EU hosts were
  available for all of these, e.g. L4 from $0.27 and RTX 4090 from $0.44.
- A stopped instance's GPU "can be rented by another user", and restarting
  may fail until a new instance is created.
- "Hosts can technically access files on their machines"; Vast advises
  verified datacenters ("Secure" icon) for sensitive data.

**Comparison.** Per session, Vast.ai is roughly a third to half of Scaleway's
cost (about $0.55–1.10 against €1.75), but at a few sessions a month both are
a few euros. The deciding factors are privacy (an unknown host holding the
table's audio, against a French cloud provider), start-up reliability (a
rented-away GPU on Vast) and the engineering work Parakeet itself needs, not
price. Against a hosted streaming speech-to-text vendor, either GPU option
adds boot time before each session and a server to maintain.

**A cheaper Scaleway non-GPU alternative [verified].** Scaleway's Generative
APIs offer `whisper-large-v3` transcription at **€0.003 per audio minute**
(€0.36 per 2-hour session), with 60 free minutes to try. That is request/file
transcription, not a live stream, and has no diarization. Voxtral Small was
deprecated there on 2026-07-01 and reached end of life on 2026-08-01, with
`/audio/transcription` requests routed to Whisper.

## What this means for Carl

These are observations for tickets 06 and 13, not decisions.

- **Scaleway doesn't displace Cloudflare as the best fit.** Its serverless
  products have the same 60-minute ceiling as Cloud Run. To get 2-hour
  connections on Scaleway you run an Instance, which puts it with Hetzner and
  Fly.io as an "ordinary server" option, with all of the operations work.
- **Where Scaleway is the better choice:** if Carl's backend must be a
  container in any language (a vendor SDK that needs Node.js or Python) *and*
  the owner wants an EU-owned provider, a STARDUST1-S or DEV1-S Instance plus
  Object Storage costs about €4–11 a month. Owner-only access would then be
  Carl's own login or Cloudflare Access in front.
- **The 6-month deletion rule maps onto Scaleway lifecycle rules as cleanly
  as onto R2**, with the same "up to 24 hours late" caveat, for cents a
  month.
- **Self-hosting Parakeet is feasible but not cheap in effort.** A Scaleway
  L4 at ~€1.75 per session is affordable at Carl's scale and keeps the audio
  with an EU provider. It needs start/stop automation, a streaming wrapper and
  a separate diarization model. Vast.ai is cheaper per hour but a poor home
  for private conversation audio. Unless a hosted vendor fails on Finnish,
  this is a later experiment, not the first build.

## Sources

Scaleway (documentation pages also available as `.md`, per
https://www.scaleway.com/en/docs/llms.txt):

- Serverless Containers limitations: https://www.scaleway.com/en/docs/serverless-containers/reference-content/containers-limitations/
- Serverless Functions limitations: https://www.scaleway.com/en/docs/serverless-functions/reference-content/functions-limitations/
- Serverless Containers FAQ (WebSockets, billing example): https://www.scaleway.com/en/docs/serverless-containers/faq/
- Serverless Containers autoscaling: https://www.scaleway.com/en/docs/serverless-containers/reference-content/containers-autoscaling/
- Securing a container (secrets, private): https://www.scaleway.com/en/docs/serverless-containers/how-to/secure-a-container/
- Authentication for private containers: https://www.scaleway.com/en/docs/serverless-containers/how-to/create-auth-token-from-console/
- Custom domain on a container: https://www.scaleway.com/en/docs/serverless-containers/how-to/add-a-custom-domain-to-a-container/
- Serverless pricing: https://www.scaleway.com/en/pricing/serverless/
- Instances pricing: https://www.scaleway.com/en/pricing/virtual-instances/
- Instances FAQ (billing, IPv4 price): https://www.scaleway.com/en/docs/instances/faq/
- Network pricing (IPs, Edge Services): https://www.scaleway.com/en/pricing/network/
- Storage pricing: https://www.scaleway.com/en/pricing/storage/
- Object Storage lifecycle rules: https://www.scaleway.com/en/docs/object-storage/how-to/manage-lifecycle-rules/
- Object Storage FAQ (lifecycle timing, classes, trial): https://www.scaleway.com/en/docs/object-storage/faq/
- Object Storage concepts (regions, bucket website): https://www.scaleway.com/en/docs/object-storage/concepts/
- Bucket website: https://www.scaleway.com/en/docs/object-storage/how-to/use-bucket-website/
- Edge Services FAQ: https://www.scaleway.com/en/docs/edge-services/faq/
- Secret Manager FAQ: https://www.scaleway.com/en/docs/secret-manager/faq/
- Secret Manager pricing: https://www.scaleway.com/en/pricing/security-and-account/
- GPU pricing: https://www.scaleway.com/en/pricing/gpu/
- Choosing a GPU Instance type: https://www.scaleway.com/en/docs/gpu/reference-content/choosing-gpu-instance-type/
- Generative APIs supported models and deprecations: https://www.scaleway.com/en/docs/generative-apis/reference-content/supported-models/
- Generative APIs pricing: https://www.scaleway.com/en/pricing/model-as-a-service/

NVIDIA:

- Parakeet TDT 0.6B v3 model card: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3

Vast.ai:

- Pricing overview: https://vast.ai/pricing
- Billing: https://docs.vast.ai/documentation/instances/pricing
- Managing instances (stopped GPUs, host access): https://docs.vast.ai/documentation/instances/manage-instances
- Offer search API used for the price snapshot [api]: https://console.vast.ai/api/v0/bundles/

Cloudflare: see the sources in [hosting-small-backend.md](hosting-small-backend.md).
