# Step 2: Utterance splitting

Type: task
Status: open
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

- [ ] pytest covers every rule, in Finnish and English examples.
