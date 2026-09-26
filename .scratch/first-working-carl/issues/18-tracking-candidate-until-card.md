# Tracking a candidate until its card

Type: grilling
Status: resolved
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
- From [Splitting verdict confidence into plain, hedged and silent](10-confidence-bands.md#answer): a candidate's card waits for both fact-finders up to ~12 s after the first draft outcome, plus a ~3 s page download for fact-finder A's excerpt and the parallel verdict and agreement calls. That wait counts toward check time and the 20 s late-card cut-off.

## Answer

Settled with the owner in a grilling session (2026-09-26).

**Noticing a settle: a separate settle call**

1. While at least one candidate is **live** (being checked, waiting for the
   screen, or on screen), each utterance also gets a small typed **settle
   call**, alongside the decision call and on the same model and context
   window. Choices: `none / settles Cn` over the live candidates only, each
   listed by its standalone restatement; an on-screen candidate also shows its
   card's fact, and for it the choices are `agrees with Cn` / `disputes Cn`.
   Threshold 0.5 (config).
2. The settle call waits until every earlier utterance's decision is known,
   so a candidate flagged two seconds ago isn't missed.
3. The candidate's own speaker correcting themselves settles it. "Let's look
   it up" and "I'm not sure" don't.
4. Rejected: a `settles Cn` choice in the decision call (a settling utterance
   is often also a new claim, and the choices are exclusive) and a second
   field in the decision call (probabilities for two fields at once are
   unverified for Luna and Jev).

**What a settle does** (see **settled** in `CONTEXT.md`)

5. **Before the card is on screen:** the candidate is dropped. Its checks are
   cancelled or their results discarded, a card already sent to the page is
   withdrawn, and the recording keeps `silent:settled` with the settling
   utterance's id.
6. **The settling utterance** goes through the decision model like any other
   and, if it is a claim, gets its own check. So a right correction ends
   silent, while a false correction or a wrong answer to an open question
   gets its own card, as the spec requires.
7. **On screen:** `agrees` adds the "Settled at the table" / "Ratkesi
   pöydässä" mark. `disputes` adds no mark, and the disputing utterance is
   not checked separately, since the card on screen already answers it. The
   mark never appears when the table got it wrong.
8. A card in the card history never changes.

**Concurrency: no queue**

9. Each candidate is its own independent task on the server, with its own
   state: finding → checking → ready → on screen / card history / silent /
   dropped / failed.
10. A safety cap of **8 live candidates** (config). Beyond it, a new
    candidate fails with an `overload` failure-log entry, so a repeat of it is
    re-checked later.
11. A hard timeout: a candidate not finished **60 s** after its utterance has
    failed (config).

**Late cards and the card history**

12. The 20 s cut-off is measured **at the moment the card would reach the
    screen**: a card that can't reach it within 20 s of its utterance (ready
    late, or waiting behind another card) is a late card and goes straight
    into the card history. The **late card** definition in `CONTEXT.md` is
    updated to match.
13. The card history is always ordered by utterance time, newest on top,
    on-time and late cards alike. The server sends each card with its
    utterance time.
14. The page reports back when each card was shown or filed, so the
    recording holds the true check time.

**Pacing**

15. The **page** runs the pacing, since the taps happen there; the server
    holds each card's state and re-sends it after a reconnect.
16. With another card waiting, the current card stays at least **8 s**
    (config), and a tap moves on at once. With none waiting it stays until
    tapped away.
17. Waiting cards are shown in utterance order; one that passes the 20 s
    cut-off while waiting goes into the card history.

**Left for later:** the ~12 s wait for the second fact-finder plus the ~3 s
page download (from [Splitting verdict confidence](10-confidence-bands.md))
press hard on both the 20 s cut-off and the 4 s median check-time target.
That is tuning for the comparison map, not a decision here.

No ADR: every choice is a prompt or config change away from reversal.

