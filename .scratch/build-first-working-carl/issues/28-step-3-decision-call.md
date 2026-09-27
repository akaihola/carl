# Step 3: The decision call

Type: task
Status: resolved
Blocked by: 23, 27

Part of [step 3](04-step-3-decision-model.md). The
[First working Carl spec](../../first-working-carl/spec.md#5-decision-repeats-and-settling) is the source of truth.

## What to build

- `prompts/decision.md` from the step-0 draft, and its example cases under
  `prompts/examples/` with a script that runs them by hand.
- One decision call per utterance, each running to the end; the backchannel
  skip; the context (up to 10 earlier utterances from the last 2 minutes,
  speaker labels, "(paused)" and "(gap)" markers, place and local time, the
  session's earlier candidates C1…); the outcome from probabilities
  (repeat, candidate, none); card language
  ([Card language](../../first-working-carl/spec.md#card-language)); cost metering; and the recording
  of every call, candidate, repeat and card language.
- Candidates are recorded, not shown.

## Done when

- [x] pytest covers the backchannel skip, the context, the repeat and
      candidate thresholds, card language and the cost, with a fake model.
- [x] The example cases have been run by hand against the configured model.

## Answer

Built on 2026-09-27: `src/carl/decision.py`, `src/carl/language.py`,
`prompts/decision.md`, `prompts/examples/decision.toml` and its runner
`carl examples [decision]` (`src/carl/examples.py`), with
`tests/test_decision.py` and `tests/test_language.py`. Both items under
"Done when" are met.

- **`prompts/decision.md`** is the step-0 draft, plus one sentence on the
  speaker labels and the "(paused)"/"(gap)" lines. Its `none` already asks
  for `none` when a claim's subject can't be worked out from the window.
  `FILLS` has `decision` with no placeholders, so startup fails without it.
- **Install:** `decision.install` checks the config's `stages.decision`
  (provider, parameters, key) at startup and sets `sessions.decider`. The
  adapter itself is made on the first call, since its HTTP session needs
  the running event loop. Without `OPENAI_API_KEY` it logs a warning and
  installs nothing, so a local run still works; note that any other
  `ValueError` from the adapter (an unknown parameter) also only warns.
- **Each utterance** gets its own task (`Sessions.on_utterance` spawns it),
  running to the end; a newer utterance never cancels one. An utterance
  made only of backchannel words (lower-cased, punctuation stripped from
  each end of each word, no minimum word count) logs `decision skipped`
  and still shows in later calls' context.
- **The fields**, in this order: `place_and_time` (the locator's
  `place_and_time(session, with_place=True)` when location is installed,
  otherwise the local date, time and timezone from `session.timezone`,
  UTC for an unknown one); `earlier_candidates` (`C1: …` per candidate,
  the whole session, by its `restatement` once step 4 sets one, the raw
  utterance until then; `(none yet)`); `conversation` (up to 10 utterances
  heard before this one in the session's list, none more than 120 s before
  it, never later ones, with the markers between them; a marker with
  nothing before it in the window is left out; `(nothing said before)`);
  `utterance`. Lines are `A1: text`: stream 1 is A, stream 2 B… (then AA),
  so labels are unique across streams. Choices are `claim`, `open
  question`, `same as C1…Cn` and `none`.
- **The outcome** (`decision.outcome`): the `same as` keys together at the
  repeat threshold make a repeat of the most likely named one, or of the
  chosen answer as it is when the mass is only pooled `same as *`;
  otherwise `claim` + `open question` at the candidate threshold make a
  candidate of the more likely kind (claim on a tie); otherwise `none`.
  With no probabilities, the chosen answer is taken as it is.
- **A candidate** (`decision.Candidate`) gets the next id C1, C2…, its
  kind, the utterance's `Heard`, the probability of its kind, its card
  language, `restatement` None and state `recorded`, and is appended to
  `session.candidates`. Ids follow the order decisions finish in.
- **Card language** (`carl.language`): the language with the most words
  over the last 600 s of utterances up to and including the candidate,
  from each word's language code (words without one aren't counted); the
  candidate's own language (most of its words, the first to appear on a
  tie) below 50 words or on a tie. Recorded with `rule` (`most words`,
  `too few words`, `tie`) and the window's and the candidate's counts.
- **Cost:** every call, failed ones included, is charged to the month as
  stage `decision` at `record.charged_usd` with `estimated` and the call's
  start time, and added to the session's cost.
- **A failed call** drops its utterance: it is recorded, charged, logged
  as a warning without conversation content, and never retried.
- **The recording** gets, per judged utterance: `model call` (the
  utterance id, the choices offered and the call record: prompt name and
  version, the fields filled in, params, model, response, tokens, cost and
  whether estimated, time, and on failure the typed error with the
  provider's full text; the rendered request is left out, as the spec
  says, since name, version and fields rebuild it); then `candidate` (id,
  kind, utterance, probability, card language with counts) or `repeat`
  (utterance, the candidate matched, probability); then `decision` (the
  utterance, the outcome `candidate`/`repeat`/`none`/`dropped`, the chosen
  answer and the probabilities, or the error). Skipped ones get
  `decision skipped`.

**Example run, 2026-09-27,** `carl examples decision` against GPT-6 Luna
with prompt d64708e0: 16 of 16 as expected, $0.00077 in all, 1.6–2.4 s a
call (all 16 ran side by side).

| Case | Expected | Got | Probabilities |
| --- | --- | --- | --- |
| en-claim, fi-claim | claim | claim | 1.00; 0.97 (none 0.03) |
| en-open-question, fi-open-question | open question | open question | 1.00 |
| en-short-disagreement ("'89 or '90?"), fi-short-question ("Kuka se oli?") | open question | open question | 1.00 |
| en-opinion, fi-opinion, fi-small-talk, en-private-fact | none | none | 1.00 |
| fi-unclear-subject, en-unclear-subject-after-pause | none | none | 1.00 |
| en-repeat | same as C1 | same as C1 | 1.00 |
| fi-repeat-across-languages (English C2) | same as C2 | same as C2 | 1.00 |
| en-same-topic-new-claim, fi-same-topic-new-claim | claim | claim | 1.00 |

Luna's probabilities are mostly one-hot, but not always: fi-claim came
back claim 0.97, none 0.03.

**Left for later steps:** the "Can't check" count and the failure log
(step 7; the `decision` event's `dropped` outcome is there to count);
checking a repeat of a failed candidate as a new one (steps 4 and 6).
`Session.end` cancels its tasks, so a decision call still running at End,
and the utterances flushed by End's own finalise, are neither recorded nor
charged.
