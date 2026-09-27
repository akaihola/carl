# Step 3: Location

Type: task
Status: resolved
Blocked by: 23, 24

Part of [step 3](04-step-3-decision-model.md). The
[First working Carl spec](../../first-working-carl/spec.md#12-location) is the source of truth.

## What to build

- The page: the Location switch on the Start screen (on the first time,
  then remembered), `watchPosition` while the session runs and not while
  paused, a fix sent first and then after a move of more than 500 m or when
  accuracy moves up a level, a denial noted once, and the disclosure's
  location clause following the switch.
- The server: reverse geocoding with Nominatim (its own User-Agent, cached,
  at most 1 request a second, again only outside the last neighbourhood
  and at most once a minute), the accuracy cuts (worse than 1 km: town
  only; worse than 20 km: none), the place context each stage gets, and
  every raw fix and geocoder response in the recording. Coordinates never
  go to any model.

## Done when

- [x] pytest covers the accuracy cuts, the geocoding rules and the place
      context, with a fake geocoder.

## Answer

Built on 2026-09-27: `src/carl/location.py`, the page (`src/carl/web/geo.js`,
`app.js`, `index.html`, `style.css`), a Location section in
`docs/websocket.md`, and `tests/test_location.py` against a fake Nominatim
on localhost. The item under "Done when" is met.

- **The page.** The Location switch sits under "Record this session", on
  the first time and then remembered in `localStorage` (`carl.location`).
  Its line credits "Place names © OpenStreetMap contributors", as
  Nominatim's usage policy asks. The disclosure's location clause follows
  the switch, and `start.disclosure.text` is read from what is shown.
  `start` carries `"location": true|false`. With the switch on, the page
  runs `watchPosition` (`enableHighAccuracy: false`, `maximumAge` 60 s)
  after the microphone opens, stops it on Pause and at End, and starts it
  again on resume. It sends the first fix, then one only after a move of
  more than `new_fix_distance_m` from the last fix sent or a better
  accuracy level. A fix waits until the server has confirmed the session,
  so one taken during a drop goes after the rejoin. A denial is sent once
  and the page doesn't ask again in that session; a new session asks again.
  With the switch off, no geolocation call is made at all.
- **The server** (`sessions.locator`, a `Locator`):
  - `on_message(session, message)` returns at once; geocoding runs as the
    session's own task, so audio never waits behind it.
  - **Nominatim** (`Nominatim`): `/reverse`, `format=jsonv2`, `zoom=14`,
    User-Agent `Carl (+https://github.com/akaihola/carl)`, no
    `Accept-Language`, so names come as Nominatim gives them. It sends one
    request at a time over all sessions, each at least 1 s after the last
    one ended. It caches answers by coordinates rounded to 3 decimals (about
    100 m), which are also all Nominatim is sent. `CARL_NOMINATIM_URL`
    points it at another server without a new build, as the policy asks.
  - **The rules:** a session geocodes again only when a fix falls outside
    the last answer's bounding box and at most once a minute
    (`geocode_min_interval_s`). A fix that comes too soon waits, and the
    latest fix is geocoded when the minute is up. A failure keeps the last
    place and is tried again after 1, 2, 4… minutes, up to 30. "Unable to
    geocode" (the open sea) is an answer: no place, not asked again for
    that fix.
  - **The cuts:** accuracy worse than 1 km gives the town only, worse than
    20 km no place. A neighbourhood found from a poor fix stays a town
    until a good fix falls inside its box.
  - `session.place` is a `Place` (neighbourhood, city, region, country,
    country code), or None. Address fields map as neighbourhood ←
    `neighbourhood`, `suburb`, `quarter`, `city_district`; city ← `city`,
    `town`, `village`, `municipality`; region ← `state`, `region`, `county`;
    country ← `country`, and `country_code` in capitals.
  - **What each stage gets:** `place_and_time(session, with_place=…)`,
    `openai_user_location(session)` (always a dict, with the timezone at
    least, so OpenAI's search never falls back to the US),
    `perplexity_user_location(session)` (None without a country), and the
    module's `date_time(timezone)`: the server clock in the phone's
    timezone, UTC when the name is unknown.
  - **Records:** a recording's event log gets `location fix` (the raw fix
    and its level), `geocoder` (the query, `source` nominatim or cache, the
    time and the full response), `geocoder failed` (kind, status and the
    full text), `location denied` once, and `place` at each change.
    Coordinates are nowhere else: the server log names only the session and
    the failure's kind, and a session's coordinates are dropped at End.
- **Live check, 2026-09-27:** one request for 60.1841, 24.9497 through
  `Nominatim.reverse` answered in 0.63 s with the quarter Linjat (its
  bounding box) inside the suburb Kallio, giving
  `Place("Kallio", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")` and
  the name "Kallio, Helsinki, Suomi / Finland". A second lookup nearby came
  from the cache. Without `Accept-Language`, Finland's country name is
  OSM's bilingual "Suomi / Finland".
- **The page in Chromium** (Playwright against a local server with a fake
  Nominatim): 53 checks passed. They covered the switch on the first
  visit and remembered after reloads, the disclosure clause and the text
  sent, no geolocation call with the switch off, the fixes sent and thinned
  by distance and level, Pause and End stopping the watch, the denial sent
  once, the server's place and context, and no request to another origin.
