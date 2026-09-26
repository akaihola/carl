# Tracking a candidate until its card

Type: grilling
Status: open
Blocked by: 09, 10

## Question

How does Carl follow a candidate from the decision model to the screen? Specifically:
- How does it notice the table settling a claim or open question: correcting the claim, answering the question, or ending a "1953 or '54?" disagreement? What counts as settled when the table's correction is itself false?
- What happens then: the candidate is dropped before its card, or the card on screen gets the "Settled at the table" / "Ratkesi pöydässä" mark.
- How do in-flight checks run concurrently, with no single-flight queue (a previous-Carl lesson)?
- How is a late card filed into the card history at its utterance time?
- How do cards pace on screen when several are ready close together?

## Comments

- From [Decision model context and candidate de-duplication](09-decision-context-and-dedup.md#answer): the decision model already gets the session's earlier candidates as a list with Carl's own ids (C1…) and answers `none / claim / open question / same as Cn`. Settling could extend that same choice list (e.g. `settles Cn`) rather than add a stage. Each earlier candidate is listed by the fact-finder's standalone restatement once one arrives. A candidate that failed at a stage is re-checked on a repeat; every other repeat gets nothing.
