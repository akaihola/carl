# Audio reaches the server about 1.2% slower than real time

Type: research
Status: open

Found on 2026-09-27 with `carl owner tail --checks`, in the owner's first
phone session, `20260927T175631Z-308317`: the one in ticket
[03](03-step-2-recorder.md)'s comments, with Finnish talk (a podcast)
playing beside the phone, on the deployed image `558c6b7` (the session
start's `commit`). It ran from 17:56:31 to 19:02:09 UTC, 65.6 minutes, on
one speech-to-text stream. Its event log has no `pause`, `page gone`,
`session suspended` or `stt rotate` event.

Over the session the audio fell steadily behind the wall clock. Carl dates
each utterance by where it ends in the audio (`Heard.time`, the stream's
start plus the utterance's `end_ms`, `session.py:728`), so every utterance
looked older than the one before by the time Carl heard it. The last one,
58.5 minutes in, reached the decision model 44.1 s after the moment Carl
gave for its end. The candidate timeout and card ages count from that moment, so the
growing gap counts against both.

## What was measured

All on 2026-09-28, from the session's whole event log in the bucket
(`read_events` in `carl.owner`: 17,989 events), with the owner's key.

**Audio arrival.** The `audio` events give each audio object's size and
`start`, the server's time when its first chunk arrived. 65 objects hold
3890.3 s of audio (64 full minutes and 50.3 s). From the first chunk
(17:56:33.008) to the session's end (19:02:09.824) is 3936.8 s of wall time,
so audio arrived at 0.9882 of real time: 46.5 s short. Consecutive
one-minute objects arrived 60.15–61.52 s apart (median 60.68, mean 60.710).
There were no jumps: the shortfall builds up evenly.

**Transcript lag.** For each `utterance` event: the event's time minus
(the stream's `stt open` time plus the utterance's `end_ms`). That is how
long after Carl's time for its end the utterance reached the decision
model. The first column counts from U1's event.

| About | Utterance | Lag |
| --- | --- | --- |
| 0 min | U1 | 0.7 s |
| 10 min | U30 | 13.0 s |
| 20 min | U69 | 16.5 s |
| 30 min | U107 | 29.7 s |
| 40 min | U150 | 30.8 s |
| 50 min | U175 | 37.7 s |
| 58.5 min | U196, the last, at 18:55:07 | 44.1 s |

A least-squares line through all 196 utterances rises 0.715 s a minute,
with residuals of standard deviation 1.7 s (from −2.0 to +5.6 s). That is
the audio's own shortfall: each minute of audio took 60.71 s to arrive.

**Candidates.** The 82 candidates were flagged 9.7 s (C1) to 44.2 s (C82)
after their utterance's end: the transcript lag plus the decision call.

## What it did to the checks and the cards

- **The candidate timeout.** A check gets `timeout_s` (60 s) from its
  utterance's `Heard.time` (`checks.py:337`), so it lost what the lag had
  eaten before it started. C80 and C82, near the end, failed with
  `timeout` while waiting on fact-finder A, at `after_s` 60.0. The other 80
  ended within the time left: 68 silent, 9 with a card sent, 3 dropped.
- **Late cards.** A card's age also counts from `Heard.time`
  (`session.py:131`), and the page files a card that can't reach the
  screen within `late_card_s` (20 s) straight into card history. All 9
  cards sent were filed late, so none came up as the current card. Each
  card's age at sending splits into the time before its candidate was
  flagged, which holds the lag, and the check itself (`candidate` event
  to `card sent`):

  | Card | Flagged after | Check | Age when sent |
  | --- | --- | --- | --- |
  | C11 | 15.2 s | 10.8 s | 26.0 s |
  | C30 | 18.3 s | 10.0 s | 28.3 s |
  | C35 | 19.1 s | 10.6 s | 29.7 s |
  | C60 | 32.4 s | 20.3 s | 52.7 s |
  | C61 | 33.7 s | 13.3 s | 47.1 s |
  | C70 | 39.3 s | 18.6 s | 57.9 s |
  | C74 | 39.1 s | 14.5 s | 53.6 s |
  | C77 | 40.8 s | 7.1 s | 47.9 s |
  | C78 | 41.1 s | 7.0 s | 48.1 s |

  Every check but C60's took under 20 s; the flagging delay grew with the
  lag.
- **Once the lag passes 60 s**, `max(0.0, left)` gives every new check no
  time at all, and each candidate fails with `timeout` before a fact-finder
  can answer. At the measured 0.715 s a minute that is after about 80
  minutes of listening (arithmetic, not measured). Ticket
  [38](38-test-material-sessions.md)'s session 1 runs 2 h 20 min.

## Two explanations, not yet told apart

1. **The phone captures fewer samples than real time.** The page asks for
   `AudioContext({sampleRate: 16000})` (`web/mic.js`) and the browser
   resamples the microphone's 48 kHz (the session start's `mic` settings),
   or the audio clock runs slow, or the worklet misses render quanta. Then
   nothing is really late: speech reaches the server promptly and only
   Carl's audio-based clock falls behind the wall clock. The timeouts and
   card ages would then be measured wrong.
2. **The phone captures in real time but sends ever later.** Chunks queue
   somewhere in the page (a throttled main thread between the worklet and
   `ws.send`, or the socket's buffer). Then the delay is real: after an
   hour the table would see a card at least 44 s after the claim, and what
   was queued at End would be lost.

What the log says:

- **No burst at End.** The last object, 50.3 s of audio, arrived over 51.4 s
  of wall time (19:01:18.442 to the `session end` at 19:02:09.824). A
  WebSocket keeps order, so audio queued in the socket's buffer would have
  reached the server ahead of the End message, in a burst. That rules out a
  queue in the socket. It doesn't rule out one before `ws.send`: once the
  session is over, the page drops any chunk it still holds
  (`mic.onchunk`, `web/app.js:411`).
- Otherwise the log can't tell the two apart. Chunks carry no time from the
  page, and both leave the same shortfall. The even growth fits a steady
  rate mismatch, but a steadily growing queue would look the same.

## How to tell them apart

- **The page reports its own count.** Add to the heartbeat the samples
  captured since Start and the `performance.now()` time elapsed since
  Start, and log them. About 16,000 samples a second means capture keeps up
  and the shortfall is in sending (explanation 2); fewer means explanation
  1. The socket's `bufferedAmount`, `document.visibilityState` and the
  `AudioContext`'s own `sampleRate` in the same message would show where a
  queue builds up.
- **A talking clock, with no code change.** Play a talking clock, or any
  audio that says an accurate time of day, beside the phone for 20
  minutes. The time each utterance says, against its `utterance` event's
  time, is the real delay. If that delay stays at a few seconds while the
  transcript lag above grows, it is explanation 1.
- `carl dev-send` into a local server paces its audio by the computer's
  clock against a fixed timeline (`play` in `carl.devsource`), so an hour's
  run with no lag would clear the server and Soniox.

## Also seen: fact-finder A's own timeouts

A separate delay, not the audio's: 8 of fact-finder A's calls hit its own
30 s limit ("no answer within 30 s (TimeoutError)", `failure` events) on
C39, C46, C47, C48, C50, C55, C57 and C82. In each, A had already missed
`second_finder_wait_s` (12 s) after B's answer, so C39–C57 were decided on
B alone (six silent with `not-found`, C55 with `claim-right`); C82 had
already failed with the candidate timeout.

## Done when

- [ ] The cause is shown by a measurement: explanation 1, 2 or another.
- [ ] A ticket for the fix, or a note here on why none is needed.

## Comments
