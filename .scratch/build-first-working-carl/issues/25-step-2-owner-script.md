# Step 2: The owner script's list, export and delete

Type: task
Status: open
Blocked by: 22

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#the-owner-only-script) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

`carl owner list`, `carl owner export <id>` (the audio joined into one WAV
file, the event log, and the corpus Markdown if there is one) and
`carl owner delete <id>` (`recordings/<id>/` and `corpus/<id>.md`), with the
bucket key, and `--dev` for local runs' recordings.

## Done when

- [ ] pytest covers the three commands against an in-memory store, and the
      WAV plays.
