# Turning phone coordinates into a place name

Research for the ticket *Turning phone coordinates into a place name*
(`.scratch/first-working-carl/issues/19-reverse-geocoding.md`), compiled
2026-09-26. The product spec gives every stage "the date, time and the phone's
precise location, taken at session start and updated during it"
([spec](../../.scratch/purpose-and-goal/spec.md#context-carl-gets)), a
**recording session** logs every model call including the location, and the
**test corpus** keeps the location rounded to neighbourhood or town
(`CONTEXT.md`). The previous Carl sent coordinates to OpenStreetMap Nominatim
and put the street address in every prompt, without weighing the privacy cost
([previous-carl-lessons.md](previous-carl-lessons.md)).

## How this was researched, and how far to trust it

- **[verified]**: read on the provider's own page (docs, pricing, terms or
  privacy policy) on 2026-09-26.
- **[tested]**: a live call made on 2026-09-26. Only keyless public endpoints
  were called (5 Nominatim calls, 1 Photon call), with coordinates in
  Kallio (Helsinki), Tapiola (Espoo) and Multimäki (Kuopio). No keyed
  service (Google, Mapbox, HERE, OpenCage, LocationIQ, Geoapify,
  Digitransit, OpenAI, Perplexity) was called.
- **[secondary]**: from a search-engine summary or third-party page, not the
  provider's own text. Treat as unverified.
- **[inferred]**: this note's own reading of what the sources imply.
- "A few calls per session" is taken as up to ~10 reverse lookups per
  session and a few hundred per month.

## Summary table

| Service | Finland neighbourhood level | Finnish / English names | Cost at a few calls per session | Store 6 months / indefinitely | What it keeps of the coordinates | Runs in the EU |
|---|---|---|---|---|---|---|
| **Nominatim (osm.org public)** | Yes [tested] (quarter, suburb, city district) | `accept-language`; admin names translate, most neighbourhood names stay Finnish [tested] | Free; max 1 req/s; own User-Agent; caching required | Yes / yes (ODbL; geocoding results are "insubstantial extracts") | IP, request URL etc. in logs; retention not stated; queries may be analysed to improve OSM | UK and NL |
| **Nominatim self-hosted** | Same data as above | Same | Server only; ≥2 GB RAM | Yes / yes | Nothing leaves Carl's server | Wherever Carl runs |
| **Photon (komoot demo)** | Yes [tested] (`locality`, `district`) | `lang`, one language per call; dumps carry local, en, de, fr names | Free "within reasonable limit", may be throttled | Yes / yes (OSM data, ODbL) | Not documented | Not stated |
| **Photon self-hosted** | Same | Same | Server only; Finland dump 242 MB | Yes / yes | Nothing leaves Carl's server | Wherever Carl runs |
| **Digitransit (Pelias, HSL/Fintraffic/Waltti)** | Yes: `neighbourhood` (Who's On First), DVV addresses, NLS places | `lang=fi/sv/en`; falls back to default (mostly Finnish) name | Free; API key; rate limits "only restrict misuse" | Yes / yes (CC BY 4.0 + ODbL, attribution with date) | Queries analysed for statistics, development, incidents; retention not stated | Finland (HSL) |
| **Statistics Finland postal areas (local lookup)** | Postal-code area names only (e.g. "Helsinki keskusta - Etu-Töölö") | Finnish and Swedish, no English | Free; download once | Yes / yes (CC BY 4.0) | Nothing leaves Carl's server | Local |
| **Google Geocoding** | `neighborhood`, `sublocality` types exist; Finland not tested | `language=fi` / `en` | 10,000 free per month, then $5 / 1,000 | Address may be cached indefinitely only for the requesting end user's own features; lat/lng 30 days; test-corpus use unclear | Logs IP and full request URL (so the coordinates); retention "based on business needs" | Not stated |
| **Mapbox Geocoding v6** | `neighborhood`, `locality`, `place` types; Finland not tested | Finnish in "local coverage" tier | Temporary: 100,000 free per month. Permanent: $5 / 1,000, no free tier | Temporary: no storing at all. Permanent: yes / yes | IP 30 days; location data "as long as needed" | US company |
| **HERE Geocoding & Search v7** | `district` / `subdistrict` fields; Finland not tested | `lang` | ~30,000 free per month, then ~$0.88 / 1,000 [secondary] | Max 30 days, except "internal testing, evaluation, or record retention" | Privacy page not read | NL-based |
| **OpenCage** | OSM-based `suburb`, `neighbourhood` | `language`, `native` | Free trial is "testing only"; production from $50/month | Yes / yes ("even if you are no longer a customer") | Query logs deleted after 6 months; `no_record=1` keeps no query | EU (Germany, Finland) |
| **LocationIQ** | Nominatim-style `neighbourhood`, `suburb` | `accept-language`, `native` | Free: 5,000/day, 2 req/s, link-back required | Free accounts: cache ≤48 h; customers: while a customer; "You can store response data forever" (contradictory) | Stats, timestamps and IPs; query contents not addressed | US & EU datacentres |
| **Geoapify** | `suburb`, `district` result types | `lang` (ISO 639-1, incl. `fi`) | Free: 3,000 credits/day (1 per reverse call), 5 req/s, commercial use allowed | Terms found silent; OSM attribution required | Request body, headers, IP, time; successful requests generally ≤24 h | EU (Hetzner), via Cloudflare / Bunny CDN |

Details and citations follow.

## 1. OpenStreetMap-based, public and self-hosted

### Nominatim (nominatim.openstreetmap.org)

- **Usage policy [verified]** ([OSMF Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)):
  "an absolute maximum of 1 request per second"; a valid User-Agent or
  Referer identifying the application ("stock User-Agents as set by http
  libraries will not do"); "Results must be cached on your side. Clients
  sending repeatedly the same query may be classified as faulty and
  blocked"; attribution must be displayed; no reselling. The policy also
  warns against submitting "personal data or other confidential material".
  Free of charge.
- **Neighbourhood level and languages [verified]**
  ([Reverse API docs](https://nominatim.org/release-docs/latest/api/Reverse/)):
  `zoom` 13 = "village / suburb", 14 = "neighbourhood", 10 = city;
  `accept-language` picks the language order.
- **[tested]** Kallio, Helsinki (60.1841, 24.9496), zoom 18:
  - `accept-language=fi`: `road: Itäinen Papinkatu, quarter: Linjat,
    suburb: Kallio, city_district: Keskinen suurpiiri, city: Helsinki,
    state: Uusimaa, country: Suomi`.
  - `accept-language=en`: same, except `city_district: Central major
    district`, `municipality: Helsinki sub-region`, `region: Mainland
    Finland`, `country: Finland`.
  - Tapiola, Espoo (zoom 14, en): `quarter: Tapiolan keskus, suburb:
    Tapiola, city_district: Suur-Tapiola, city: Espoo`.
  - Multimäki, Kuopio (zoom 14, en): `suburb: Multimäki, city: Kuopio,
    state: North Savo`.
  - So Finland has neighbourhood names in OSM in both the capital region and
    a mid-sized town; English changes administrative and country names, but
    neighbourhood names stay Finnish because they have no English name
    [inferred from the tests].
- **Storing results [verified]**: OSM data is under the ODbL
  ([copyright page](https://www.openstreetmap.org/copyright)). The OSMF
  [geocoding guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Geocoding_-_Guideline)
  classes geocoding results as insubstantial extracts, neither Produced Works
  nor Derivative Databases; share-alike is not triggered unless the results
  are used to rebuild a substantial part of the OSM database. Storing place
  names for 6 months or indefinitely is therefore allowed [inferred].
- **Privacy [verified]** ([OSMF privacy policy](https://osmfoundation.org/wiki/Privacy_Policy)):
  logs include IP address, browser/application, referrer, time and pages
  accessed; no retention period is given for server logs ("given the
  temporary nature of this storage…"); Nominatim queries may be analysed "for
  missing addresses and postcodes" and shared with the OSM community;
  personal data is stored in the UK and the Netherlands, backups in the EU.
  From a server, OSMF sees Carl's server IP and the coordinates, not the
  phone [inferred].

### Self-hosted Nominatim

- [Installation docs](https://nominatim.org/release-docs/latest/admin/Installation/)
  [verified]: "A minimum of 2GB of RAM is required"; the 64–128 GB and 1 TB
  figures apply to a full planet. A Finland-only extract is far smaller
  [inferred]. Needs PostgreSQL/PostGIS and a periodic re-import or update.
- Nothing leaves Carl's server, no rate limit, same names as above.

### Photon (komoot)

- **Public demo [verified]** ([README](https://github.com/komoot/photon/blob/master/README.md)):
  "You are welcome to use the API for your project as long as the number of
  requests stay in a reasonable limit. Extensive usage will be throttled or
  completely banned. We do not give guarantees for availability." No privacy
  statement for the demo server was found.
- **Languages [verified]** ([API docs](https://github.com/komoot/photon/blob/master/docs/api-v1.md)):
  one `lang` per request, falling back to the server's default language then
  the local name; pre-built dumps "contain names in English, German, French
  and local language".
- **[tested]** Kallio, `lang=en`: `name: Kallio Church, street: Itäinen
  Papinkatu, locality: Linjat, district: Kallio, city: Helsinki, state:
  Uusimaa, country: Finland`.
- **Self-hosting [verified]**: Java 21+; GraphHopper publishes a weekly
  [Finland dump](https://download1.graphhopper.com/public/europe/finland/index.html)
  of 241.7 MB (updated 2026-09-21/24). A planet needs ~95 GB disk and 64 GB
  RAM; a Finland-only instance needs a small fraction [inferred].
- Storing: OSM data, same as Nominatim.

## 2. Finnish public sources

### Digitransit geocoding (Pelias)

Sources: the Digitransit docs site returned a Cloudflare challenge, so these
were read from its source repository
[HSLdevcom/digitransit-site](https://github.com/HSLdevcom/digitransit-site)
(`src/pages/en/developers/...`) [verified].

- **Endpoint**: `https://api.digitransit.fi/geocoding/v1/reverse?point.lat=…&point.lon=…`
  with `lang` = `fi`, `sv` or `en`, `size`, and filters by layer
  (`address`, `venue`, `street`, `neighbourhood`, `localadmin`, …) and source
  (`oa` = DVV address data, `osm`, `nlsfi` = National Land Survey, GTFS).
  Response fields include `neighbourhood` (e.g. *Itä-Pasila*), `locality`,
  `localadmin`, `region` and a display `label`.
- **Languages**: returns the name in the preferred language "if such a
  language-bound name version is available, otherwise using the default
  name … Most default names are of course in Finnish."
- **Data**: neighbourhoods and admin areas come from Who's On First, plus OSM,
  DVV addresses and NLS place names
  ([pelias-data-container](https://github.com/HSLdevcom/pelias-data-container)).
- **Access and limits**: an API key from the
  [Digitransit API portal](https://portal-api.digitransit.fi/) sent as the
  `digitransit-subscription-key` header or parameter. Rate and quota limits
  since 2024-01-31 "should only restrict misuse of the APIs, not normal use."
  Free: "Digitransit is not charging any fees on joining and utilizing API."
- **Terms**: data under CC BY 4.0 ("free use of the data to any purpose,
  including right to copy, rework and distribute"), attribution with the date
  of retrieval (e.g. "© Digitransit 2021"); OSM-based parts under ODbL.
  Storing 6 months or indefinitely is allowed [inferred].
- **Privacy**: the API is "managed by tools that enable analyzing of the data
  query for purpose of statistics, development and incident management". No
  retention period in the terms; the
  [HSL privacy policy](https://www.hsl.fi/hsl/tietosuoja) was not read.
- Operated by HSL, Fintraffic and Waltti in Finland; Finnish law applies.
- Not tested (needs a key).

### Statistics Finland postal-code areas (lookup on Carl's own server)

- Statistics Finland's WFS `geo.stat.fi/geoserver/postialue/wfs` serves
  3,018 postal-code area polygons for 2026 (`pno_2026`) with Finnish
  (`nimi`) and Swedish (`namn`) names, e.g. `00100` "Helsinki keskusta -
  Etu-Töölö" / "Helsingfors centrum - Främre Tölö", and the municipality
  code [tested: one WFS feature request]. Published under CC BY 4.0
  ([Statistics Finland open data](https://stat.fi/fi/palvelut/tilastodatapalvelut/avoin-data-ja-rajapinnat))
  [secondary: search summary of stat.fi pages].
- Downloaded once, a point-in-polygon lookup on the server needs no external
  call per session, so no coordinates leave Carl [inferred]. Names are
  postal-area names (sometimes two joined), not always what people call the
  neighbourhood; no English names; Finland only.

## 3. Commercial services

### Google Geocoding API

- **Price [verified]** ([pricing](https://developers.google.com/maps/billing-and-pricing/pricing)):
  SKU "Geocoding", Essentials category, 10,000 free events per month, then
  $5.00 per 1,000 (10,001–100,000). Default quota 3,000 queries per minute
  ([usage and billing](https://developers.google.com/maps/documentation/geocoding/usage-and-billing)).
- **Names [verified]** ([reverse geocoding requests](https://developers.google.com/maps/documentation/geocoding/requests-reverse-geocoding)):
  `language` supports `fi` and `en`; result types include `neighborhood` and
  `sublocality_level_1…5`. Finnish neighbourhood coverage not tested.
- **Storing [verified]**: a billing account in the EEA gets the
  [EEA Service Specific Terms](https://cloud.google.com/terms/maps-platform/eea/maps-service-terms).
  Geocoding API §6.2: lat/lng may be cached up to 30 days; "latitude (lat),
  longitude (lng), formatted_address, and the structured address values"
  may be cached indefinitely "solely to support the direct, End User facing
  functionality of the Customer Application that initiated the request …
  Cached data must be logically isolated to the specific End User … and must
  not be used across multiple End Users." §6.1 forbids use "With any Map"
  other than lat/lng/place_id. Whether logging the address into a recording
  session or a test corpus used to measure Carl counts as "End User facing
  functionality" is not clear; a cautious reading says it does not
  [inferred]. Place IDs may be stored indefinitely
  ([policies](https://developers.google.com/maps/documentation/geocoding/policies)).
  Google Maps attribution is required when results are shown.
- **Privacy [verified]** ([security and compliance](https://developers.google.com/maps/security/compliance/security-compliance)):
  "All Google Maps Platform requests are logged", including the IP address
  and "Request URL: which contains the API and parameters being passed",
  i.e. the coordinates; "may be retained for various lengths of time based
  on business needs"; no period given.

### Mapbox Geocoding v6

- **Names [verified]** ([Geocoding API docs](https://docs.mapbox.com/api/search/geocoding/)):
  feature types `neighborhood`, `locality`, `place`; Finnish is in the
  "local coverage" tier ("almost always present for country, region, and
  prominent place features"). Finnish neighbourhood coverage not tested.
- **Storing [verified]**: "Temporary results are not allowed to be cached,
  while Permanent results are allowed to be cached and stored indefinitely."
  Permanent needs `permanent=true` and a credit card on file.
- **Price [verified]** ([pricing](https://www.mapbox.com/pricing)):
  temporary: 100,000 free per month, then $0.75 / 1,000. Permanent: no free
  tier, $5.00 / 1,000 (so ~$0.05 for 10 calls). Rate limit 1,000 requests per
  minute by default.
- **Privacy [verified]** ([privacy policy](https://www.mapbox.com/legal/privacy)):
  IP addresses kept 30 days (longer for investigations); location
  information kept "for so long as Mapbox determines it is needed", with
  anonymisation mentioned but no timeline for geocoding queries.

### HERE Geocoding & Search v7

- **Price [secondary]**: the Base plan is quoted as 30,000 free
  transactions per month, then about $0.88 per 1,000; HERE's own
  [pricing page](https://www.here.com/get-started/pricing) renders its
  numbers client-side and could not be read. A credit card is needed for
  the Base plan [secondary].
- **Names**: `revgeocode` takes `at`, `lang` and `types`; addresses carry
  `district` and `subdistrict`
  ([docs](https://docs.here.com/geocoding-and-search/docs/introduction-to-here-geocoding-search-api-v7))
  [verified, summary level]. Finland not tested.
- **Storing [verified]** ([HERE platform terms, Sept 2023](https://www.here.com/en-gb/terms/here-platform-terms-september-2023),
  §6 j): you may not "Cache or store outside of the Platform any Results …
  for more than 30 days, … unless Results are used solely for your internal
  testing, evaluation, or record retention for audit and legal compliance
  purposes." Recording sessions (6 months) and the test corpus exceed 30
  days; whether measuring Carl counts as "internal testing, evaluation" is a
  reading of the terms [inferred]. Whether a newer version of these terms
  exists was not checked.
- **Privacy**: HERE's service privacy page returned 404; not verified. HERE
  Global B.V. (Eindhoven, NL) is the controller [secondary].

### OpenCage

- **Price and limits [verified]** ([pricing](https://opencagedata.com/pricing)):
  free trial 2,500 requests/day, 1 req/s, but "testing only" ("If you
  decide to use our service in production you should become a paying
  customer"); X-Small $50/month (10,000/day, 15 req/s); one-time plans also
  exist (price not read).
- **Storing [verified]**: "You can store the data returned by the API
  permanently. Even if you are no longer a customer."
- **Names [verified]** ([API docs](https://opencagedata.com/api)):
  `language` (IETF tag or `native`); OSM-style components including
  `suburb` and `neighbourhood`; reverse returns one result.
- **Privacy [verified]** ([GDPR page](https://opencagedata.com/gdpr), edited
  2026-07-22): German company; geocoding servers in the EU (Germany and
  Finland); "Geocoding queries are deleted after six months and are never
  used to train AI"; with `no_record=1` "we will not store your query when
  we log the request."

### LocationIQ

- **Price and limits [verified]** ([pricing](https://locationiq.com/pricing)):
  free plan 5,000 requests/day, 2 req/s, 60/minute; "Limited Commercial
  Use … if you spread the love by adding a prominent link back to us";
  paid from $45/month (maps only) or $100/month.
- **Names [verified]** ([reverse API](https://docs.locationiq.com/reference/reverse-api)):
  zoom 14 = suburb; `accept-language` (default `en`, or `native`);
  `normalizeaddress=1` gives `neighbourhood` and `suburb`.
- **Storing [verified]** ([terms](https://locationiq.com/tos)): "If you have
  a free account, you can cache request-response pairs from the Service for
  upto 48 hours. If you are a customer, you can cache request-response pairs
  for as long as you're a customer. You can store response data forever."
  The last sentence and the first two pull in different directions; ask
  LocationIQ before relying on it [inferred].
- **Privacy [verified]** ([privacy policy](https://locationiq.com/privacy)):
  collects API usage stats, request counts, timestamps and IP addresses; it
  does not say whether query contents are logged or for how long. US & EU
  datacentres.

### Geoapify

- **Price and limits [verified]** ([pricing](https://www.geoapify.com/pricing/),
  [pricing details](https://www.geoapify.com/pricing-details/)): free
  3,000 credits/day, up to 5 req/s, commercial and production use allowed
  with attribution; a reverse geocoding request costs 1 credit.
- **Names [verified]** ([reverse geocoding docs](https://apidocs.geoapify.com/docs/geocoding/reverse-geocoding/)):
  `lang` (ISO 639-1, `fi` included); `result_type` values include `suburb`
  and `district`.
- **Storing**: no clause on storing results was found in the
  [terms](https://www.geoapify.com/term-and-conditions/) [verified that it
  is absent from the page text]; OSM attribution is always required,
  Geoapify attribution on the free plan.
- **Privacy [verified]** ([privacy policy](https://www.geoapify.com/privacy-policy/)):
  EU business, servers at Hetzner; for every request it keeps "the request
  body, headers, IP address, and timestamp", and "data for successful
  requests is held for no longer than 24 hours". Traffic passes Cloudflare,
  and Bunny CDN for the `.eu` domain.

## 4. Do the search tools take a user location?

### OpenAI web search (Responses API) [verified]

From the [web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
and the [Create a response reference](https://developers.openai.com/api/reference/resources/responses/methods/create):

- `tools: [{ type: "web_search", user_location: { type: "approximate",
  country, city, region, timezone } }]`.
- `country` is a two-letter ISO code; `city` and `region` are free text;
  `timezone` is an IANA name (e.g. `Europe/Helsinki`).
- **No coordinates field.** Only place names.
- "If omitted or null, defaults to the United States. To avoid this
  fallback, pass `{"type": "approximate"}` without location fields."
- Not supported for deep research models.

So the OpenAI fact-finder needs at least a city name and country from a
reverse lookup, and should always send `user_location` so it doesn't default
to the US [inferred].

### Perplexity Agent API web search [verified]

From the [Agent API web search docs](https://docs.perplexity.ai/docs/agent-api/tools/web-search):

- `user_location` sits in the `web_search` tool object alongside `filters`:
  `{ country: "US", region: "CA", city: "San Francisco", latitude: 37.7749,
  longitude: -122.4194 }`.
- `country` is ISO 3166-1 alpha-2; `city` and `region` "significantly
  improve location accuracy"; "`latitude` and `longitude` must be provided
  together with `country`. They cannot be supplied on their own."

So Perplexity accepts coordinates directly (with a country), and does better
with city and region too [verified]. Whatever is sent is received by
Perplexity and, per its model routing, possibly the model provider
[inferred].

## 5. Trade-offs to weigh (not decisions)

- **Privacy vs effort.** Only self-hosted Nominatim/Photon, or a local
  polygon lookup, keeps coordinates off third parties. Among hosted ones,
  OpenCage (`no_record=1`, EU) and Geoapify (≤24 h, EU) state the shortest
  or most controllable retention; OSMF, Google, Mapbox, Digitransit and
  LocationIQ give no fixed period for query contents. Note that the search
  providers receive whatever location Carl passes them anyway.
- **Storage terms vs recording sessions and the test corpus.** OSM-based
  services, Digitransit, OpenCage and Mapbox Permanent allow keeping results
  indefinitely. Mapbox Temporary forbids storing at all; HERE allows 30 days
  unless the testing/evaluation exception applies; Google allows indefinite
  caching only for the end user's own features, which is a doubtful fit for
  a test corpus; LocationIQ's free tier caps caching at 48 h.
- **Cost.** At a few calls per session every option is free or pennies,
  except OpenCage (production needs a $50/month plan) and Mapbox Permanent
  (~$5 per 1,000).
- **Names.** Finnish names come from every OSM-based service and Digitransit
  (tested for Nominatim/Photon only). English neighbourhood names mostly
  don't exist; English mainly changes country, region and district labels.
  Swedish is available from Digitransit and Statistics Finland.
- **Nominatim's own rules** (1 req/s, caching required, no personal data)
  fit a few calls per session, but the policy asks users not to send
  personal data, and a home's coordinates arguably are [inferred].
- **Search tool formats differ**: OpenAI needs city/region/country/timezone
  text; Perplexity takes coordinates plus country. A reverse lookup to city
  level is needed at least for OpenAI.

## Not checked

- Finnish neighbourhood results from Google, Mapbox, HERE, OpenCage,
  LocationIQ, Geoapify and Digitransit (no keys).
- HERE's current price list and privacy policy; the HSL privacy policy;
  komoot's privacy terms for the Photon demo; OpenCage one-time plan prices.
- Whether a Finland-only Nominatim or Photon fits within Carl's chosen host
  (Scaleway Serverless Container, scaled to zero) in memory and cold-start
  time.
