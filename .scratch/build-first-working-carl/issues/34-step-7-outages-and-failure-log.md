# Step 7: Can't hear, can't check and the failure log

Type: task
Status: resolved
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

## Answer

Built on 2026-09-27, server side: `src/carl/outages.py` (new: `FailureLog`
and each session's `Health`), wired into `session.py`, `server.py`,
`decision.py`, `settle.py`, `checks.py` and `recording.py`, with
`tests/test_outages.py` (24 tests). The suite passes (724) apart from
`tests/test_corpus.py`, whose `corpus.py` another agent is writing.

- **"Can't hear"**, one reason code each, in the order they win:
  `connection` (the page's socket closed or went silent; it clears when
  audio arrives on the new socket, or at the rejoin while paused),
  `mic-lost` (the page's `mic` message, until `back`), `no-audio` (while
  listening, connected and with the microphone live, no chunk for
  `no_audio_s`, until the next one; a watchdog task per session) and
  `stt-reopening` (speech-to-text dropped or didn't open, until a stream is
  open). The handover is a rejoin on a second socket while the first is
  open, so the first one's close is no drop and nothing flickers. Pause ends
  `no-audio` and `stt-reopening`; long silence is none of these.
- **"Can't check"**: `decision` after `decision_failures` (3) failed calls in
  a row, settle calls counted with decision calls; `fact-finding` and
  `fact-checking` after `check_failures` (2) failed candidates in a row. A
  candidate fails at fact-finding only when every fact-finder fails on it,
  and at fact-checking only when a failed call leaves it without a band; a
  candidate that made no fact-checking call leaves that count alone. The
  60 s timeout counts against the stage it was stuck in; `overload` counts
  for nothing. A stage clears on its first success. The decision outage's
  entry counts the utterances dropped since the model last worked (each
  still got its call).
- **The indicator** goes to the page as `indicator` when it changes and
  after `start` and `rejoin`, "Can't hear" winning. The recording mark
  (`recording` in `session`) is off while no audio can reach the server
  (`connection`, `mic-lost`, `no-audio`) or storage (the recorder's last
  write failed, `Recorder.failing`), and a `session` message now also goes
  out whenever it changes (noted in `docs/websocket.md`). It stays on
  through `stt-reopening`, since audio still reaches the recording.
- **The failure log** (`Sessions.failures`): `failures/<UTC date>.jsonl`,
  rewritten whole on each write (one instance owns it), records queued and
  written by a task, a failed write kept for the next, flushed at shutdown.
  An entry has the time, session id, stage, kind (`bad-output` spelling),
  provider and model, HTTP status, error code and candidate id, and nothing
  else: no conversation content, no provider text. An outage is written when
  it starts and again when it ends, under one id, with its problem, reason,
  stage, start, end and, for `decision`, `utterances_skipped`. Every
  `Session.failure` call (decision, settle, each fact-finder, verdicts, the
  agreement call, `overload`, the timeout, speech-to-text) goes there, and a
  recording's event log gets a copy of each entry with the provider's full
  error text, and of each outage. Starting outages without a failed call of
  their own get their entry then: `connection`/`dropped`, `mic`/`mic-lost`,
  `mic`/`no-audio`.
- **The page's buffer** (`page_events`): a `gap` becomes a `connection`
  outage and a `mic-lost` a `mic` outage in the failure log, with the page's
  start and end and `source: "page"`; every event (hidden, wake lock, a card
  that failed to render included) goes to the event log, keeping only short
  known fields.
- **Speech-to-text**: a dropped stream now reopens at once, then after 1, 2,
  4… 30 s while opening keeps failing (it used to retry every second). A
  stream open for `ROTATE_AFTER_S` (280 minutes) is replaced at its next
  segment end: the new one opens while the old one still takes the audio,
  then the old one closes and the context gets "(gap)"; if the new one
  doesn't open, the old one carries on until the next segment end.
- **Tests** cover each threshold and rule above, with short config values:
  the failure log's files, rewriting and retry; no provider text in entries;
  three decision failures (with a settle call among them), a success
  resetting the count, two candidates failing at each check stage, one
  fact-finder down, `overload`, the timeout; which problem wins; the
  recording mark with no audio and with storage down; through the WebSocket,
  the indicator after start, no audio (and not while paused), a dropped
  connection clearing only when audio flows, the handover with no drop, the
  microphone lost and back, and the page's buffer; the reopen backoff, a
  dropped stream's "(gap)", and rotation at a segment end.
