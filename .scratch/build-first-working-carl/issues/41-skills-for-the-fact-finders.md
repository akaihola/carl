# Skills for the fact-finders, starting with routing

Type: grilling
Status: open
Waiting on: owner

Not part of the first working version. The owner raised it while marking
session `20260928T081440Z-bf362b` of the test corpus.

At 00:00:54 A2 asked which of the Ruoholahti and Lauttasaari metro stations
is the longer walk from where they sat (C3). The question came back twice,
at 00:04:10 with an address, Hillilaiturinkuja 2. Both fact-finders
answered `not found`, and Carl stayed silent.

The [product spec](../../purpose-and-goal/spec.md#triggers) counts such
situational questions as open questions ("is the pharmacy on the corner
open on Sundays?"). The fact-finders can only search the web, though, and
no web page gives a walking distance from a table. A map with routing
does, and OpenStreetMap is a public source.

The owner's idea: give the fact-finders skills beyond web search, with
routing first.

## To settle

- Which skills come after routing? For example: opening hours from
  OpenStreetMap, timetables from Digitransit, weather from FMI, and date
  arithmetic. C6 of the same session was hedged because its excerpt gave
  Stubb's birth date and the fact-checker had to work out his age.
- Routing needs the table's coordinates, but today the search tools get
  place names only, never coordinates
  ([spec, Location](../../first-working-carl/spec.md#12-location)). Can
  coordinates go to a routing provider, and which one?
- A route has no page to take an excerpt from. What does the card cite, and
  what does the fact-checking model judge it against
  ([ADR 0001](../../../docs/adr/0001-typed-judges-around-a-writing-search.md))?
- Should both finders get the skills, or only one? Two finders only mean
  something when they reach their answers independently.
- The 00:04:10 repeat brought a new address but was folded into C3, so it
  got no new check. A repeat that adds what the first try lacked may
  deserve a new check.

## Comments
