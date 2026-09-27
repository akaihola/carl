# Step 7: Resuming after a restart

Type: task
Status: resolved
Blocked by: 34

Part of [step 7](08-step-7-robustness.md). The
[First working Carl spec](../../first-working-carl/spec.md#session-continuity) is the source of truth.

## What to build

- Session state saved to `sessions/<id>/state.json` as it changes: recent
  utterances, open candidates, cards shown, the running cost and the current
  place name (never coordinates).
- At every start, each saved session's page gets the 2-minute grace period to
  reconnect, then the session ends as usual; checks lost in the restart are
  logged as `lost-in-restart`; the state is deleted at End.

## Answer

Built on 2026-09-27: `src/carl/resume.py` (new: `snapshot`, `restore`,
`SessionStates`), with `Session.keep_saved`, `suspend` and `carry_on` in
`session.py`, `Recorder.continue_after`, the startup and shutdown hooks in
`server.py`, `resume.install` in `cli.py`, and `tests/test_resume.py` (10
tests; the whole suite, 860, passes).

- **What is saved** to `sessions/<id>/state.json`: the id and the page's
  start id, start time, timezone, listening or paused, whether it records
  and whether the recording was stopped, listening time (with the start of
  the current stretch, so the state only changes when the session does),
  running cost, stream and utterance counts, the utterances the decision
  context can still reach (at most 10, none older than 2 minutes, with
  their markers), every candidate (id, kind, state, probability,
  restatement, card language, its utterance, and the failed one it
  repeats), every card sent with its state and times, which utterances
  disputed a card, and the current place name. Never coordinates: the
  locator keeps those in memory only. Older utterances aren't kept, so after
  a restart the card language counts only the saved ones, falling back to
  the candidate's own language sooner.
- **When:** each session saves in its own task, at once after a change that
  matters (a candidate flagged or changing state, a card sent, reported or
  withdrawn, Pause, resume, a recording stop), otherwise every 3 s, writing
  only when something changed. End stops the saving, waits for a save under
  way, and deletes `sessions/<id>/`. The bucket's 1-day rule is the
  backstop.
- **At startup** (`on_startup`, before serving) every saved state is rebuilt
  as a live session: its grace period starts again, the indicator is "Can't
  hear" (`connection`, detail `restart`), the context gets "(gap)", a
  recording carries on under the same prefix after the parts already
  written (with a `session resumed` event), and a candidate that was
  `finding` or `checking` fails as `lost-in-restart` against its stage, so a
  repeat of it is checked anew. No speech-to-text stream opens until the
  page rejoins, so nothing is paid for with nobody there. A rejoin gets
  `session`, `indicator` and `cards` (a ready card again in `waiting`); a
  start resent with the same start id finds the session too. A session whose
  page doesn't come back ends as usual after the grace period. A state that
  can't be read is logged and left for the bucket's rule.
- **At a graceful shutdown** (`close_sockets`), each live session is
  suspended instead of ended: its stream closes (charged), open outages end,
  its state is saved, its recording written out (a `session suspended`
  event, no `session end`), its tasks cancelled; then the failure log is
  flushed and the sockets closed with 1001. Utterances flushed while
  suspending are saved but start no decision call. Without saved states (as
  in tests that don't install them), a shutdown still ends every session.
  Scaleway's scale-to-zero comes only after 15 minutes without requests,
  when the grace period has long ended every session, so in practice this
  path serves redeploys.
- **The settle call** now lists live candidates by utterance time rather than
  by position in the context, so candidates from before a restart count.
- **Tests:** the round trip, with no coordinates in the state and only the
  context's utterances; saving at once after a change, not again when
  nothing changed; a saved session resumed at startup with no stream until
  the rejoin, its `session`, `indicator` and `cards`, the stream opening at
  the rejoin with fresh labels, the indicator clearing with audio, the
  pre-restart cost and listening time in the summary, the recording
  continuing without overwriting, `lost-in-restart` in the failure log and
  the recording, and the state deleted at End; the end after the grace
  period with no stream ever opened; an unreadable state; a resent start;
  a shutdown saving instead of ending, with 1001, and the next instance
  resuming the session; a shutdown without saved states; a repeat of a
  lost candidate checked anew.
