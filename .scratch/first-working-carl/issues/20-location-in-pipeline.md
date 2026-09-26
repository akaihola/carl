# Location in the pipeline and the test corpus

Type: grilling
Status: open
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
