# Step 7: Resuming after a restart

Type: task
Status: open
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
