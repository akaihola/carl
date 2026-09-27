# Step 2: Recording and cost metering

Type: task
Status: resolved
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

- [x] pytest covers the audio objects, the log parts, stop-and-delete, the
      month split and the euro rate, against an in-memory store.

## Answer

Built on 2026-09-27 in `src/carl/recording.py` and `src/carl/costs.py`,
with `tests/test_recording.py` and `tests/test_costs.py` against the
in-memory store.

- **Audio:** `recordings/<id>/audio/<n>.pcm`, `n` six digits from 1. The
  chunks are kept exactly as queued and never split, so an object ends at
  the first chunk that brings it to a minute (`AUDIO_OBJECT_BYTES`), or
  early at `audio_break()`. Each object gets an `audio` event when it ends:
  `key` (relative to the prefix), `start` (when its first chunk was queued)
  and `bytes`. The session should call `audio_break()` before it logs
  `session end`, so that the last object's event comes before it.
- **Events:** each `flush()` writes the queued lines as the next
  `events/<n>.jsonl` part. Each line is `{"time", "event", ...fields}`,
  with `time` like `2026-09-27T18:02:11.123Z` and UTF-8 left unescaped. A
  field can't be called `time`. `run()` flushes every 10 s, and `close()`
  writes everything, the unfinished audio object included.
- **Failed writes** stay queued and are logged. The next flush tries them
  again under the same key, so a part that failed is rewritten whole, with
  the lines queued since. An audio object that fails holds back the ones
  behind it, so they keep their order. `close()` tries 3 times, 1 s apart,
  then logs an error with what couldn't be written.
- **Stop and delete:** the stop first stops accepting and drops what is
  queued. A put already sent can't be called back (boto3 runs it in a
  thread), so the stop then waits for every put under way and deletes all
  of `recordings/<id>/` after that. Each put runs as its own shielded task,
  so cancelling `run()` or a flush can't hide a put that is still landing.
  A stop can be sent again, and works after `close()` or from a fresh
  `Recorder`.
- **Costs:** `month_key()` gives the Europe/Helsinki month, with a naive
  time taken as UTC. `stream_cost()` is `audio_hour / 3600 * seconds`, and
  `to_eur()` divides by `ecb_usd_per_eur`. `Costs` reads each month once,
  keeps it in memory and rewrites `costs/month-YYYY-MM.json` on every
  charge, under a lock. The object holds `month`, `usd`, `estimated_usd`,
  `by_stage`, `by_provider`, `charges` and `updated`. A failed write keeps
  the charge in memory, and the next charge writes it. A failed read
  raises and overwrites nothing. A negative or non-finite cost is refused.
