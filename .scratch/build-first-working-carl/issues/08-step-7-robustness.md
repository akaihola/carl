# Step 7: Robustness

Type: task
Status: open
Blocked by: 07

Build step 7 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. This step is probably too big for one agent
session. Split it into further tickets in this folder before starting.

## What to build

- **"Can't hear"** ([Can't hear](../../first-working-carl/spec.md#cant-hear)):
  - the page–server connection drops: the WebSocket closes, or 10 s pass
    with no message. The server likewise treats 10 s from the page as a drop
    and starts the grace period.
  - the microphone is lost: the track ends or is muted, permission is
    revoked, or the page is hidden;
  - the speech-to-text connection drops;
  - no audio chunk for 5 s while listening.
  - The planned handover, Pause and long silence are not failures.
  - It clears once audio flows end to end again.
- **"Can't check"** ([Can't check](../../first-working-carl/spec.md#cant-check)):
  - the decision model after 3 failed calls in a row, counting decision and
    settle calls together;
  - fact-finding or fact-checking after 2 failed candidates in a row.
    Fact-finding fails for a candidate only when both fact-finders fail on
    it.
  - One fact-finder down is not "Can't check": only hedged cards are
    possible then.
  - `overload` never changes the indicator.
  - It clears on the stage's first success, with no health probes.
  - Utterances during a decision outage are dropped and counted. Each one
    still gets its decision call.
- **The indicator** ([One state, two wordings](../../first-working-carl/spec.md#one-state-two-wordings)):
  - the striped orange pill, worded "Can't hear" or "Can't check" from the
    server's reason code, with "Can't hear" winning;
  - no error text on screen;
  - the recording mark shows only if audio still reaches storage.
- **The failure log** ([The failure log](../../first-working-carl/spec.md#the-failure-log)):
  - entries with the time, stage, kind, provider and model id, HTTP status
    or provider error code, session id and candidate id;
  - outages with a start, an end and the number of utterances skipped;
  - no conversation content and no free-text provider message;
  - stored under `failures/` (30 days), and copied into a recording
    session's event log with the full error text;
  - wired to the `overload` and timeout failures from step 6.
- **The page's buffer** ([What the page buffers](../../first-working-carl/spec.md#what-the-page-buffers)):
  the connection gap, the microphone being lost, the page being hidden, the
  wake lock refused or released, and a card that failed to render. They are
  sent on reconnect.
- **Resuming from `state.json`** ([Session continuity](../../first-working-carl/spec.md#session-continuity)):
  - the session state saved to `sessions/<id>/state.json` as it changes:
    recent utterances, open candidates, cards shown, running cost and the
    current place name;
  - at every start, the server gives each saved session's page the 2-minute
    grace period to reconnect, then ends it;
  - checks lost in the restart are logged as `lost-in-restart`;
  - the state is deleted at End.
- **The handover at about 50 minutes, with no gap** ([Hosting](../../first-working-carl/spec.md#hosting)):
  - the page opens a second WebSocket, moves the audio onto it and closes
    the old one;
  - the server's speech-to-text stream stays open;
  - a new socket that fails to open counts as a dropped connection.
- **Reopening Soniox, and rotation** ([The speech-to-text stream](../../first-working-carl/spec.md#the-speech-to-text-stream)):
  - a dropped stream reopens at once, backing off 1, 2, 4… up to 30 s, with
    fresh speaker labels and a "(gap)" marker;
  - the recording keeps writing audio meanwhile, and the event log marks
    the gap;
  - a stream nearing Soniox's 300-minute limit is replaced at the next
    segment end.

## Done when

- [ ] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: the "Can't hear" and "Can't check" rules
      and their thresholds, failure-log entries and outages, resuming from
      saved state, and the Soniox backoff.
- [ ] Deployed and used for one session on the phone of more than an hour,
      at a real dinner or with a Finnish radio talk show playing beside it,
      so the handover runs. Its event log shows no gap at the handover.
- [ ] A dropped connection, a Pause and a server restart have each been
      tried by hand, and each showed the right state and recovered.
