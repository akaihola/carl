# Step 3: Location

Type: task
Status: open
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

- [ ] pytest covers the accuracy cuts, the geocoding rules and the place
      context, with a fake geocoder.
