# Step 2: The owner script's list, export and delete

Type: task
Status: resolved
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

- [x] pytest covers the three commands against an in-memory store, and the
      WAV plays.

## Answer

Built on 2026-09-27 in `src/carl/owner.py`, with tests in
`tests/test_owner.py`.

- `carl owner list [--dev]` prints a plain table, newest first: the session
  id, its start in Helsinki time (from the id, or the start event), the
  duration, the size and notes. The duration is the end event's
  `listening_s`; a session with no end event (still running, or the server
  stopped) shows the length of its audio, marked `~`. A session whose
  recording has expired but whose `corpus/<id>.md` is kept is listed as
  "corpus only", since the corpus is personal data too.
- `carl owner export <id> [--out DIR] [--dev]` writes `DIR/<id>/`
  (`~/carl-exports` by default, outside the repo so a recording can't be
  committed by mistake): `audio.wav`, every audio object joined in order as
  16 kHz mono 16-bit PCM through the stdlib `wave` module; `events.jsonl`,
  every log part joined in order; `corpus.md` if there is one; and anything
  else under `recordings/<id>/` as it is.
- `carl owner delete <id> [--yes] [--dev]` shows the session and asks
  `[y/N]` unless `--yes` (warning when there is no end event, as the
  session may still be recording), removes `recordings/<id>/` and
  `corpus/<id>.md`, lists both again to check nothing is left, and prints
  how many objects went.
- Ids must be whole: `YYYYMMDDTHHMMSSZ-` and 6 lowercase hex digits, a real
  date, or `export` and `delete` refuse them, so a typo can't name a wider
  prefix.
- The bucket key is read from the environment or `.secrets.bucket.env` at the
  repo root, the environment winning. The store is built in `owner.py`, so
  CARL_CLOUD doesn't matter: prefix `""` for the cloud's recordings, `dev/`
  with `--dev`. Without a bucket key, `--dev` reads `.carl-store/`, where a
  local run without one writes.
- Sizes come from the bucket's own listing (`list_objects_v2`), so `list`
  downloads only the first log part and the last few of each session.
  `session end` is looked for in the last three parts, because the recorder
  writes the last audio object's event at close, after the end, and it can
  land in a part of its own.
- pytest covers the three commands against a `MemoryStore`, a round trip
  through the real `Recorder`, the WAV read back with `wave` (parameters and
  frames), delete touching nothing else, bad ids refused, the bucket key's
  sources, and the bucket listing through botocore's `Stubber`.
