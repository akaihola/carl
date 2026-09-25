# What runs in the browser and what runs on a server

Type: grilling
Status: resolved
Blocked by: 01, 02, 03, 04

## Question

Which parts of the pipeline and of Carl's state run in the phone's browser and which on a server, if any? Covers who calls each model provider (and so who holds keys), where session state (utterances, candidates, cards) lives, and what survives a dropped connection.

## Answer

Settled with the owner in a grilling session (2026-09-25).

1. **Thin page, pipeline on a server.** The page does microphone capture and
   audio streaming, the screen, the wake lock, location, and the Start, Pause
   and End taps. The server does everything else: speech-to-text, splitting
   finals into utterances, the decision, fact-checking and message-writing
   models, de-duplication, the drop rule, late cards, cost metering and
   recording. All provider keys and the swappable model interfaces live only
   on the server, speech-to-text included, so a self-hosted model (e.g.
   Nemotron streaming, see [parakeet-v3.md](../../../docs/research/parakeet-v3.md))
   can plug in behind the same interface. Audio takes one extra hop (tens of
   ms inside the EU).
2. **A network drop loses its gap.** The listening indicator shows "can't
   hear or check", the failure log records the gap, and no audio is buffered
   or replayed. A recording keeps exactly what the live pipeline saw; a gap
   caused by a drop still counts as "recorded completely".
3. **Dropped connection versus closed page.** The page sends End on
   `pagehide` when it can. Otherwise the server keeps the session for a
   **2-minute grace period** waiting for the page to reconnect, then ends it.
   Checks already running continue during the drop. **The server is the
   source of truth for the session's cards:** on reconnect it re-sends the
   current card and the card history, and the page rebuilds its screen. A
   card that became ready during the drop follows the normal late-card rule
   (more than 20 s after its utterance → card history).
4. **A server restart resumes the session.** The server saves session state
   as it changes (recent utterances for the decision context, open
   candidates, cards shown, running cost). After a restart the page
   reconnects as in 3 and the session carries on. Checks lost in the restart
   go to the failure log.
5. **Pause.** The page stops the microphone track (so the phone's own mic
   indicator goes off) and tells the server. The server closes the
   speech-to-text connection and reopens it on resume; a heartbeat keeps the
   page–server link open meanwhile. Checks started before Pause finish and
   their cards are shown.

No ADR: a key-holding server running the pipeline is what every vendor
recommends, so it is not surprising.
