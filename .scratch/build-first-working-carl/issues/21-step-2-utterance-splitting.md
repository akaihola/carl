# Step 2: Utterance splitting

Type: task
Status: resolved
Blocked by: 

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#from-final-segments-to-utterances) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

`src/carl/utterances.py`: pure logic that turns one stream's final words
into utterances: split at every speaker change, merge runs of 2 words or
fewer between runs by the same speaker, and split an utterance longer than
about 30 s at the next sentence end.

## Done when

- [x] pytest covers every rule, in Finnish and English examples.

## Answer

Built on 2026-09-27 in `src/carl/utterances.py`, with 36 tests in
`tests/test_utterances.py`, in Finnish and English.

- `Splitter(false_switch_max_words, longest_s)` takes one stream's final
  words in order through `add(words)` and returns the utterances they
  complete. `endpoint()` returns everything still held, and the next word
  starts afresh: nothing merges across a segment end.
- Words are grouped into runs by speaker label, left to right. When a
  speaker speaks again after a run of 2 words or fewer by someone else, that
  run is a false switch: the three runs become one utterance by the
  surrounding speaker, at once. Merged words keep their own speaker label,
  as the recording does.
- A run is held until it can't be part of a merge any more: until the next
  speaker has said more than 2 words, a third speaker starts, or the segment
  ends. So a held utterance waits for at most 2 more words, or the endpoint.
  A short run at the start or end of a segment, or between two different
  speakers, is an utterance of its own.
- Conflicting merges are decided left to right: in A B(1) A(1) B, the first
  B merges into A, so A(1) is no longer between two B runs.
- An utterance is split after the first word ending in ".", "?", "!" or "…"
  whose end is at least 30 s after the utterance's first word started.
  It is emitted as soon as that word is known to be its speaker's, together
  with anything held before it, and the rest carries on as the same
  speaker's next utterance. So a false switch right after a split joins the
  words that follow it, rather than standing alone.
- A false switch's own words count: if a merged-in "Joo." is the first
  sentence end past 30 s, the split falls after it, when the speaker
  returns.
- A speaker change still ends an utterance at once, past 30 s or not, and a
  monologue with no sentence end waits for the endpoint.
- Known limit: a word like "6." (a Finnish ordinal) or "esim." counts as a
  sentence end, so a split past 30 s can fall mid-sentence. The split only
  changes where the decision model's utterance ends, and it gets the
  previous utterances as context.
