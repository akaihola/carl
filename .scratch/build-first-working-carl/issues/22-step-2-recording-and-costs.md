# Step 2: Recording and cost metering

Type: task
Status: open
Blocked by: 

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#what-a-recording-keeps) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

- `src/carl/recording.py`: audio objects of about one minute and a JSONL
  event log written in parts about every 10 s, under `recordings/<id>/`
  (`dev/` for local runs), and the one-way stop that deletes it all at once.
- `src/carl/costs.py`: speech-to-text stream cost from the price table, the
  month-to-date total in `costs/` by Europe/Helsinki calendar month, stored
  in USD and shown as ≈€ at the config rate
  ([Cost metering](../../first-working-carl/spec.md#11-cost-metering)).

## Done when

- [ ] pytest covers the audio objects, the log parts, stop-and-delete, the
      month split and the euro rate, against an in-memory store.
