# Step 7: The page: indicator, buffer and handover

Type: task
Status: resolved
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

## Answer

Built on 2026-09-27, in `src/carl/web/` (`app.js`, `link.js`, `mic.js`,
`cards.js`, `style.css`), to `docs/websocket.md`'s "Can't hear, can't
check". Checked against a mock of it; ticket 34 builds the server's side.

- **The indicator** is one state: the connection down (socket closed, or
  nothing heard for `silence_s`, or a rejoin under way) is "Can't hear";
  else Pause is "Paused"; else the microphone lost or the page hidden is
  "Can't hear"; else the server's `indicator` (`cant_hear` over
  `cant_check`); else "Listening". Both problems are the striped orange
  pill. The `reason` code is kept nowhere on screen. The step-2 "Connection
  lost, reconnecting…" is gone from the indicator (the Start screen's note
  keeps it). The Recording pill follows the server's `recording`, and is
  hidden while the page knows no audio reaches the server: the connection
  down or the microphone lost.
- **The microphone lost** (`mic.js`): the open track's `ended`, `mute` and
  `unmute`, and the microphone permission's `change` where the browser has
  it. An ended track is `ended`, or `permission` when the permission is
  denied (a later denial updates it). The page sends `mic` `lost` with the
  detail and `back` live when it can, and says the current state again
  after every rejoin. A muted track waits for its unmute; an ended one is
  reopened at once, then every 5 s while the page is visible, not while
  the permission is denied or only askable, and again when it is granted
  or the page is visible again. Resuming from Pause with a fresh microphone
  also brings it back. Paused, a closed microphone is no loss.
- **The page's buffer**: the connection gap (from the drop to the next
  `session` reply), the microphone lost, the page hidden (start and end),
  the wake lock `refused` or `released` by the browser (not the page's own
  release at End), and a card that failed to render (each once; `cards.js`
  now reports it through a callback). Events go in `page_events` once the
  server has confirmed the session on the current connection: straight
  away while connected, else in one message after the rejoin's `session`
  reply. At End, what is still open is closed and sent before `end`.
- **The handover** (`link.js`): about `handover_s` after a socket's hello,
  a second socket opens. When it says hello, the page sends `rejoin` on it
  (or, with no session, just moves over); from then on audio is held and
  other sends refuse, as while the connection is down, until the answer on
  the second socket: then the held audio goes on it in order, the old
  socket closes, and the page squares Pause taps, reports, location and
  pending stops as after a rejoin. The state stays "connected", so the
  indicator doesn't flicker. A handover waits while a start or rejoin is on
  its way. A second socket that closes, or hasn't taken over within
  `silence_s`, drops both sockets: "Can't hear" and the usual reconnect.
- Checked with Playwright in Chromium against the throwaway mock, with the
  page's audio chunks numbered as the worklet makes them (199 checks with
  the card checks). The server's "Can't check" and "Can't hear" worded,
  striped and without the reason code, the top bar fitting at 360 px; the
  page hidden winning over "Can't check"; "Can't hear" 5 ms after the
  socket closed and at 10 s of a silent server, then back; a muted, an
  ended (reopened) and a permission-revoked microphone (not reopened until
  granted), Pause winning and Resume clearing it; the `mic` messages; the
  Recording pill; each page event, and one `page_events` after the rejoin
  holding a gap, a hidden stretch, a lost microphone and a wake lock
  released and refused, with nothing sent while down; the open ones sent
  before `end`. Two handovers 10 s apart: chunks 0 to 217 arrived once
  each, in order, across three sockets, the longest arrival gap 0.11 s,
  the old socket closed 1 ms after the first rejoin, the indicator never
  leaving "Listening". A refused second socket and one whose rejoin went
  unanswered (dropped at 10.2 s) each showed "Can't hear" and recovered.
  The Start screen hands over with no rejoin and stays usable.
