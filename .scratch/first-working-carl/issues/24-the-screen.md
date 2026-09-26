# The screen

Type: prototype
Status: resolved
Blocked by: 21, 22

## Question

Turn the [fact card prototype](../../purpose-and-goal/prototypes/fact-card-prototype.html)
into the first version's real UI, as a rough clickable prototype on the
owner's Android phone:

- The Start screen: Start, the recording-session choice and disclosure, the
  month's running total and the last session's cost, access to the card
  archive and the Log menu.
- The session screen: the current card with claim/question label, hedge
  mark, "Settled at the table" mark; the card history ordered by utterance
  time; card pacing (at least 8 s when another waits, tap to move on); the
  listening indicator with listening, recording, paused and can't hear or
  check; Pause and End; the live transcript line.
- The card archive view with its owner marks, and the Log menu.

## Assets

- [Screen prototype](../prototypes/the-screen/screen-prototype.html)
  (open by double-click, or the private page
  <https://claude.ai/artifact/GfBeLrfGYkWw7K7gobKXge>): three session layouts
  (A Stage, B Split, C Frame), each with its own Start screen, plus the shared
  disclosure, Stop recording, session summary, card archive and Log screens,
  driven by a scripted Finnish dinner. Round 2 (same file and page): the
  round-1 choices below as the portrait layout P, plus three landscape
  layouts (L1 Side column, L2 Control rail, L3 Bottom shelf).

## Comments

- **Round 1 reactions (owner, 2026-09-26):**
  1. Session screen from layout B, but the indicator, Pause and End on one
     row, so the top bar is slimmer and the cards get more room.
  2. B's easily scrolled card history, in smaller type and a smaller share of
     the screen, leaving more space for the current card.
  3. End asks for confirmation (easy with a touchpad or mouse too).
  4. The striped indicator for can't hear / can't check.
  5. The Start screen from layout A.
  6. Carl's own words in English.
  7. Most phone cases hold the phone upright only in landscape, so a
     landscape layout is needed too.

- **Round 2 reactions (owner, 2026-09-26):** landscape L1 (Side column) is
  best; the one-row portrait bar and smaller history are right; Carl supports
  both orientations; the landscape Start screen is complete.

## Answer

Settled with the owner by reacting to two rounds of the
[screen prototype](../prototypes/the-screen/screen-prototype.html)
(2026-09-26).

1. **Both orientations; Carl follows the phone.** Most phone cases hold the
   phone upright only sideways, so landscape is the main case, but the same
   page lays itself out for portrait too.
2. **The session screen** (the round-2 prototype's P and L1):
   - A one-row **top bar** (new term in `CONTEXT.md`): the listening
     indicator, its recording mark, then Pause, End and a ⋯ menu at the right
     end. In landscape the live transcript line, when on, sits in the bar
     between them; in portrait it goes under the current card.
   - **The current card** takes the rest of the screen, as large as the
     spec's Spotlight card: coloured Claim/Question label, a "Hedged" tag next
     to the label plus the "Todennäköisesti:"/"Probably:" prefix, gist, fact,
     source, and the "Settled at the table" mark under it. Tap anywhere on it
     to move on. With another card waiting, "+N waiting" and a shrinking 8 s
     bar show under it.
   - **The card history** always visible and scrollable, in small type:
     a column on the right (about 30% of the width) in landscape, a strip
     along the bottom (about 30% of the height) in portrait. Ledger rows,
     newest on top, older ones dimmer; a claim is marked ≠, a question ?,
     and a hedged card has a dashed edge.
   - Between cards, only the top bar and the card history are on screen.
3. **End asks first.** Tapping End turns the top bar into "End the session?
   Cancel / End". A plain tap or click confirms it, so it works on a touchpad
   or mouse as well as a phone. The spec's "anyone taps End" still holds.
4. **The listening indicator** is a pill: green "Listening" (pulsing dot while
   someone speaks), amber "Paused", and a **striped** orange pill "Can't hear"
   or "Can't check". The recording mark is a separate red "Recording" pill
   next to it; tapping it opens "Stop recording?" (as in
   [Development mode and the recording-session disclosure](21-development-mode-and-disclosure.md#answer)).
5. **The Start screen:** a big round Start button; switches for "Record this
   session", Location and (later) the transcript line; "This month ≈ €…" and
   the last session's date, length, cost and €/h; Card archive and Log as
   small links in the top corners. Landscape puts Start on the left and the
   rest on the right. With recording on, Start opens the disclosure screen
   first.
6. **Carl's own words are in English** (labels, buttons, the Start screen,
   the Log). Cards stay in the card language, and the disclosure stays
   Finnish and English.
7. **Around it:** a "Session ended" summary (listening time, cards, cost,
   whether the recording was kept) leading back to Start; the card archive
   as a list of sessions with Wrong/Pointless marks and a missed-moments
   note; the Log as a list of entries and outages with a Clear that asks
   first. Their placement is fixed now, but "What done means" still leaves the
   settled mark, the transcript line, the card archive and the Log for later.
8. **Look:** a dark screen whatever the phone's theme, in Atkinson
   Hyperlegible, carried over from the fact card prototype.

No ADR: each choice is cheap to change in the page. `CONTEXT.md` gains
**Start screen** and **Top bar**.
