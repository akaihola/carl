# Step 7: The page: indicator, buffer and handover

Type: task
Status: open
Blocked by: 34

Part of [step 7](08-step-7-robustness.md). The
[First working Carl spec](../../first-working-carl/spec.md#hosting) is the source of truth.

## What to build

- The indicator's striped orange "Can't hear" / "Can't check" from the
  server's state; no error text on screen.
- The page's own "Can't hear": the WebSocket closed or silent 10 s, the
  microphone track ended or muted, permission revoked, or the page hidden.
- The page's buffer: the connection gap, the microphone lost, the page
  hidden, the wake lock refused or released, and a card that failed to
  render, sent on reconnect.
- The handover at about 50 minutes: a second WebSocket, the audio moved onto
  it, the old one closed, with no gap; a new socket that fails to open counts
  as a dropped connection.
