# The Worker turns away requests without an access pass

Type: task
Status: resolved

Follows [ticket 18](18-step-1-domain-and-loading-worker.md). The
[First working Carl spec](../../first-working-carl/spec.md#hosting) is the
source of truth.

Bots request `faktat.vempai.men` roughly every 10–30 minutes. Each request
wakes the container and keeps it running about 15 minutes, so it may be up
for much of the day. The owner wants the loading Worker to answer bots
without waking the container, even though that changes what the public
address does.

## What to build

- The Worker answers every request without an access-pass cookie itself,
  as Carl's gate would: the pass form (401) for a GET outside `/api/`, and
  a 401 "An access pass is needed." for anything else. Only the pass form's
  `POST /api/unlock` and requests with the cookie go through. The Worker
  only looks for the cookie; the gate checks it.
- The pass form is one file, `src/carl/pass.html`, served by the server and
  bundled into the Worker.
- The loading page only for GET page loads, since the pass form's POST now
  passes through the Worker and can't be reloaded.
- The Worker-free route narrows from `faktat.vempai.men/api/*` to
  `faktat.vempai.men/api/ws`, so bots probing `/api/…` meet the Worker too.
  The health poll now passes through it (with the cookie), a few requests
  per cold start.

## Done when

- [x] No request without the cookie reaches the container, `/api/health`
      included.
- [x] Signing in with a pass and loading the page with the cookie work, and
      the loading page still shows on a cold start.
- [x] The WebSocket still skips the Worker, and the main route still fails
      open.

## Comments

- 2026-09-27: Tested locally with `wrangler dev --local-upstream` in front
  of a stand-in that logged every request reaching it and took 4 s to answer
  when cold. Fifteen cookieless requests (`/`, `/robots.txt`, `/.env`,
  `/wp-login.php`, `/static/app.js`, `HEAD /`, `/api/health`,
  `/api/v1/pods`, `GET /api/unlock`, POSTs, an empty `carl_pass=`, other
  cookies) got the pass form or the 401 and none reached the stand-in.
  In Chromium, the pass form came from the Worker, its POST waited out the
  4 s and set the cookie, and only then did `GET /` reach the stand-in. With
  the cookie and the stand-in cold, a page load got "Starting up…" after
  2.5 s.
- 2026-09-27: Deployed (`faktat-front` version `b5250d00`), and the route
  `faktat.vempai.men/api/*` changed in place to `faktat.vempai.men/api/ws`.
  `wrangler deploy` recreated the main route without fail-open, as the
  operations doc warns, so `request_limit_fail_open` was set again. On the
  live address, the container's answers carry Scaleway's
  `x-envoy-upstream-service-time` header and the Worker's own don't:
  fourteen cookieless requests, `/api/health` and `/api/v1/pods` among
  them, got the Worker's answer without that header, while a made-up cookie
  was passed on to Carl's gate (the pass form, and `/api/health` 200). A
  wrong pass POSTed to `/api/unlock` reached the gate and was answered
  after its 1 s wait. `/api/ws` without a cookie got Carl's own 401, so the
  WebSocket still skips the Worker.
