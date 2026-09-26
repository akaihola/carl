# Turning phone coordinates into a place name

Type: research
Status: open
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
