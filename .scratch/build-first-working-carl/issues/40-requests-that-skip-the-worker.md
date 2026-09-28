# How often do requests skip the Worker?

Type: research
Status: resolved

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

## Answer

**Once a day, and it costs about 15 minutes of uptime.** Measured on
2026-09-28 at 19:51 UTC from all 72 lines the container logged since the
deploy (2026-09-27 19:47:35 to 2026-09-28 17:17:58, nothing after), fetched
through the Loki API and counted by script:

| How it came | Owner's phone | `carl-log-check` | Anyone else |
| --- | --- | --- | --- |
| Through the Worker (`cf-worker=vempai.men`) | 14 | 1 | 0 |
| Cloudflare without the Worker (`/api/ws`) | 4 | 1 | 0 |
| Straight to the container (`cf-ray=-`) | 0 | 1 | 1 |

Every access line had the new fields. No scanner reached the container
through `faktat.vempai.men`. How many the Worker turned away isn't known:
the Cloudflare token can't read analytics, and no tail was running.

The one request from anyone else:

- 2026-09-28 17:17:58, `GET /` (401), host
  `carl2255fb5c-carl.functions.fnc.fr-par.scw.cloud`, user agent Chrome 150
  on macOS. It fetched no `/favicon.ico`, as a browser would after a page,
  so it was most likely a script.

With the 19:28 request on 2026-09-27 (ticket body), that is two direct
hits in the 26 hours since the Worker started turning requests away, at
18:09 on 2026-09-27.

Cold starts, one per instance:

| Started | Woken by | How it came |
| --- | --- | --- |
| 09-27 19:47:35 | the deploy itself; then the `carl-log-check` requests and a 6 s reconnect of the phone's page at 19:57 | — |
| 09-28 08:12:18 | the phone loading the page (loading page, then a 981 s session) | the Worker |
| 09-28 09:13:59 | the phone's page reconnecting (a 199 s session) | `/api/ws` |
| 09-28 17:17:55 | the direct `GET /` above | straight to the container |

Up time, estimated as each instance's last activity plus the operations
doc's 15 minutes to scale to zero (the logs don't show the scale-down
itself): about 25, 34, 18 and 15 minutes, so about 1.5 hours in the 24,
of which about 50 minutes were the owner's sessions and 15 minutes the
direct hit. Before the Worker turned requests away, the log had scanner
traffic every 10–40 minutes (ticket 37).

**Recommendation: leave it.** A private container, with the Worker adding
Scaleway's token, would move the WebSocket and its 60-minute handover onto
the Worker to save about 15 minutes a day. Taking the address out of the
docs wouldn't take it out of the git history or out of the lists that
already have it. One day is a small sample: `|= "cf-ray=-"` in the Loki
query (operations doc, Logs) shows whether direct hits grow.

## Comments
