# Turning phone coordinates into a place name

Type: research
Status: resolved
Blocked by: 

## Question

The product spec gives every stage the phone's precise location, taken at
session start and updated during it, and the test corpus keeps it rounded to
neighbourhood or town. Which reverse-geocoding services could turn the
coordinates into a place name (street, neighbourhood, town, country) for a
server in the EU, and for each:

1. Does it cover Finland at neighbourhood level, and return names in Finnish
   and English?
2. What does it cost at a few calls per session, and what are its rate limits
   (e.g. Nominatim's usage policy)?
3. Do its terms allow storing the result in recording sessions for 6 months
   and in the test corpus indefinitely?
4. What does it keep of the coordinates it receives (privacy)?

Also: do OpenAI's web search and Perplexity's Agent API accept a user
location (coordinates or place) for localising search, and in which form?

## Answer

Full findings with citations:
[docs/research/reverse-geocoding.md](../../../docs/research/reverse-geocoding.md).

1. **Finland at neighbourhood level, Finnish and English.** OSM-based
   services have Finnish neighbourhoods: live Nominatim calls returned
   quarter, suburb and city district in Helsinki, Espoo and Kuopio (e.g.
   Linjat / Kallio / Keskinen suurpiiri), and Photon returned the same.
   English changes country, region and district labels ("Central major
   district") but neighbourhood names stay Finnish. Digitransit (Finland's
   public Pelias) has a `neighbourhood` field and `lang=fi/sv/en`.
   Statistics Finland's postal-area polygons give Finnish and Swedish
   postal-area names for a local lookup. Google, Mapbox, HERE, OpenCage,
   LocationIQ and Geoapify document neighbourhood-level types and Finnish,
   but were not tested (no keys).
2. **Cost and rate limits.** At a few calls per session nearly everything
   is free: Nominatim (max 1 req/s, own User-Agent, caching required),
   Photon demo ("reasonable limit"), Digitransit (API key, limits only
   against misuse), Google (10,000 free a month, then $5 / 1,000), Mapbox
   Temporary (100,000 free), HERE (~30,000 free, secondary source),
   LocationIQ (5,000/day with a link-back), Geoapify (3,000/day). OpenCage's
   free trial is for testing only (production from $50/month); Mapbox
   Permanent has no free tier ($5 / 1,000).
3. **Storing for 6 months and indefinitely.** Allowed for OSM-based results
   (ODbL; the OSMF geocoding guideline treats results as insubstantial
   extracts), Digitransit (CC BY 4.0), Statistics Finland (CC BY 4.0),
   OpenCage ("permanently") and Mapbox Permanent. Not allowed for Mapbox
   Temporary; HERE allows 30 days unless "internal testing, evaluation"
   applies; Google (EEA terms) allows indefinite caching only for the end
   user's own features, a doubtful fit for a test corpus; LocationIQ free
   accounts may cache 48 h, and its terms contradict themselves on storing.
4. **What they keep of the coordinates.** Self-hosted Nominatim/Photon or a
   local polygon lookup keep nothing outside Carl. OpenCage: EU servers,
   query logs deleted after 6 months, none with `no_record=1`. Geoapify: EU,
   request body/IP kept generally ≤24 h. Mapbox: IPs 30 days, location data
   "as long as needed". Google: logs the full request URL (so the
   coordinates) with no fixed period. OSMF: logs with no stated period;
   Nominatim queries may be analysed to improve OSM; its policy asks users
   not to send personal data. Digitransit and LocationIQ state no period.

**Search tools.** OpenAI's `web_search` takes `user_location: {type:
"approximate", country, city, region, timezone}`, place names only, no
coordinates, and defaults to the United States if omitted. Perplexity's
Agent API `web_search` takes `user_location: {country, region, city,
latitude, longitude}`; coordinates need `country` with them. So at least a
city-level name is needed for OpenAI, while Perplexity can take the raw
coordinates.
