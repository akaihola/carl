# How often do requests skip the Worker?

Type: research
Status: claimed

Follows [ticket 37](37-worker-turns-away-requests-without-a-pass.md). The
Worker answers every request to `faktat.vempai.men` that has no access-pass
cookie, but a request to the container's own address,
`carl2255fb5c-carl.functions.fnc.fr-par.scw.cloud`, never meets it. The
public repo names that address in `docs/operations.md` and `deploy/deploy.sh`.

On 2026-09-27 the owner's session ended at 19:02 (its page left at 19:08),
and the container went cold. At 19:28 a new instance started for three
requests with the user agent `Mozilla/5.0 (compatible)`, seen nowhere else in
the day's logs: `GET /` (401) and `GET /api/health` twice (200). Through the
Worker, a request without a cookie gets a 401 from `/api/health`, so these
most likely came straight to the container's own address.

The question: how often does that happen, and does it keep the container
awake for much of the day? The owner chose to measure before closing the
address (making the container private, with the Worker adding the token)
or taking it out of the docs.

## How

Each access-log line now ends with `host=`, `cf-ray=` and `cf-worker=`
(commit `8f6ce20`, deployed as image `cf6af56` at 19:47 UTC):
`cf-worker=vempai.men` means the Worker passed the request on, a `cf-ray`
alone means Cloudflare without the Worker (`/api/ws`), and `cf-ray=-` means
the request came straight to the container. Checked with one request of
each kind (user agent `carl-log-check`). A day of logs, read as in
[the operations doc's Logs](../../../docs/operations.md#logs), gives:

- requests of each kind, leaving out `carl-log-check` and the owner's own;
- every request with `cf-ray=-`: its time, path, host and user agent;
- every cold start (`carl.cli: starting`) and the first request after it.

A deploy starts an instance by itself, before any request (19:47:35).

## Comments
