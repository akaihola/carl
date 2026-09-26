# Location in the pipeline and the test corpus

Type: grilling
Status: resolved
Blocked by: 19

## Question

How does the phone's location reach Carl's stages and records?

- Does the page send raw coordinates, and does the server turn them into a
  place name (via which service, from
  [Turning phone coordinates into a place name](19-reverse-geocoding.md))?
- What does each stage see: the decision model, the settle call, the
  fact-finders (as text in the prompt, or as the search tool's user
  location), the fact-checking model?
- How often is it updated during a session, and what counts as a move worth
  an update?
- What happens when the owner switches location off, when permission is
  denied, or when the fix is poor (indoors)?
- How is it rounded to neighbourhood or town for the test corpus, and what
  do the raw recording and the card archive keep?

## Answer

Settled with the owner in a grilling session (2026-09-26). Facts from
[Turning phone coordinates into a place name](19-reverse-geocoding.md).

**Coordinates to place name**

1. The page sends raw coordinates with their accuracy to Carl's server; the
   server turns them into a place name. The page makes no third-party calls.
2. The server reverse-geocodes with **Nominatim** (public OSM): its own
   User-Agent, results cached, at most 1 request/s. It is free at a few calls
   per session, has Finnish neighbourhoods (tested), works abroad, and ODbL
   allows storing its results. Names are kept as returned, so neighbourhoods
   are in Finnish. The place name is neighbourhood, city, region and country.
3. Rejected: Digitransit (Finland only), a local Statistics Finland polygon
   lookup (Finland only, postal areas not neighbourhoods) and OpenCage
   (`no_record`, but $50/month for production). The coordinates already go to
   cloud services under the disclosure line, so Nominatim's logging is
   accepted.

**What each stage sees**

4. **Coordinates never go to any model.** Place context is at neighbourhood
   level, never street.
5. **Decision model** and **fact-finders**: the place name (neighbourhood,
   city, country) with the local date, time and timezone in the prompt.
6. **Fact-finders' search tools**: `user_location` built from city, region,
   country and timezone (OpenAI) or city, region and country (Perplexity), with
   no coordinates, though Perplexity would take them.
7. **Settle call** and **fact-checking model**: date and time only. A
   fact-finder must write any place a card depends on into its standalone
   restatement, so the fact-checking model sees it there.

**Updates during a session**

8. The page runs `watchPosition` while the session runs (not while paused) and
   sends a fix only when it has moved more than **500 m** from the last one
   sent, or when accuracy improves from poor to good.
9. The server re-geocodes only when the new fix falls outside the last
   result's neighbourhood, at most once a minute. At a dinner table that is
   one geocoding call per session. Thresholds live in the config file.

**Off, denied, poor fix, geocoder down**

10. The **off switch** is on the Start screen and remembered on the phone.
    When it is off, the page never asks for geolocation; stages get only date,
    time and timezone (the timezone comes from the phone).
11. **Permission denied** behaves like off, with no nag. It is noted once in
    the recording session's event log and is not a failure-log entry: Carl can
    still hear and check.
12. **Poor fix:** accuracy worse than 1 km gives stages the town only; worse
    than 20 km gives no location.
13. **Geocoder failure:** keep the last place name (none if there isn't one
    yet). It is event-logged, not failure-logged.
14. The date and time always come from the server clock, in the phone's
    timezone.

**What each record keeps**

15. **Recording session event log** (180-day deletion): every raw fix sent
    (coordinates, accuracy, time) and every geocoder response. Each model call's
    log records the place context that stage was given.
16. **Test corpus Markdown:** the header's `place:` holds neighbourhood and
    town. If the session moved, it lists each place in order. It never holds
    coordinates.
17. **Session state** (kept for resume): the current place name only, never
    coordinates. It is deleted at End with the rest of the state.
18. **Card archive, failure log and cost summaries:** no location.
19. **Normal (non-recording) session:** coordinates live only in server
    memory and are gone at End.
