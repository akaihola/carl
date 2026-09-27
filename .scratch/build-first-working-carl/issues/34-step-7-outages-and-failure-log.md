# Step 7: Can't hear, can't check and the failure log

Type: task
Status: open
Blocked by: 07

Part of [step 7](08-step-7-robustness.md). The
[First working Carl spec](../../first-working-carl/spec.md#10-failures-and-outages) is the source of truth.

## What to build

On the server:

- "Can't hear": the page's connection dropped (closed, or 10 s silent), the
  microphone lost (from the page), speech-to-text dropped while it reopens,
  or no audio chunk for 5 s while listening. Not the planned handover,
  Pause or long silence. It clears once audio flows end to end again.
- "Can't check": the decision model after 3 failed calls in a row (decision
  and settle together); fact-finding or fact-checking after 2 failed
  candidates in a row, fact-finding failing only when both fact-finders
  fail. `overload` never changes it. It clears on the stage's first
  success. Utterances during a decision outage are dropped and counted.
- The indicator's state and reason code sent to the page, "Can't hear"
  winning; the recording mark only while audio still reaches storage.
- The failure log: entries (time, stage, kind, provider and model, HTTP
  status or error code, session id, candidate id) and outages (start, end,
  utterances skipped), no conversation content and no free-text provider
  message, under `failures/`, copied into a recording's event log with the
  full error text; wired to step 6's `overload` and timeout failures.
- The page's buffered failures, received after a reconnect, go into the log.
- Soniox stream rotation before its 300-minute limit, at a segment end.
