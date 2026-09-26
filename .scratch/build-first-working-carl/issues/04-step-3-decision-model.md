# Step 3: Decision model

Type: task
Status: open
Blocked by: 03

Build step 3 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. If the step is too big for one agent session,
split it into further tickets in this folder before starting.

**Candidates** are recorded, not shown. Nothing is searched yet.

## What to build

- **The typed-answer interface and the decision model's adapter**
  ([Stage interfaces](../../first-working-carl/spec.md#stage-interfaces)):
  - named text fields, one question and an answer type in; the answer and a
    probability per choice out;
  - the model and settings that step 0 confirmed (provisionally GPT-6 Luna, a
    JSON schema allowing only the given choices, reasoning off,
    `store: false`);
  - probabilities from logprobs where the vendor has them, empty otherwise;
  - every call returns the model id, prompt version, parameters, token
    counts, cost and response time, or a typed error (`timeout`,
    `unavailable`, `rate-limited`, `bad output`). The adapter never retries.
- **`prompts/decision.md`**, starting from the step-0 draft.
- **The decision call** ([Decision, repeats and settling](../../first-working-carl/spec.md#5-decision-repeats-and-settling)):
  - one call on every utterance, each running to the end. A newer utterance
    never cancels one.
  - the backchannel skip: utterances made up only of words on the Finnish
    and English list in the config file are skipped, with no minimum word
    count. Skipped utterances still appear in later calls' context.
  - the context: the new utterance, marked; up to 10 earlier utterances from
    no more than the last 2 minutes; speaker labels and the "(paused)" and
    "(gap)" markers; the place name with the local date, time and timezone;
    the session's earlier candidates by Carl's ids (C1, C2…).
  - Until step 4 brings the fact-finders' standalone restatements, each
    earlier candidate is shown by its raw utterance.
  - choices `none / claim / open question / same as C1 … Cn`.
- **From probabilities to an outcome** ([From probabilities to an outcome](../../first-working-carl/spec.md#from-probabilities-to-an-outcome)):
  - the `same as` choices together at 0.5 or more make a **repeat** of the
    most likely one;
  - otherwise `claim` and `open question` together at the candidate
    threshold (0.5) make a candidate of the more likely kind;
  - otherwise `none`;
  - with no probabilities, the chosen answer is taken as it is.
  - Each recorded repeat links to the candidate it matched, with its
    probability.
- **Card language** ([Card language](../../first-working-carl/spec.md#card-language)):
  - the language with the most words over the last 10 minutes of final
    utterances, counted from each word's language code;
  - the candidate's own language below about 50 words or on a tie;
  - recorded for each candidate with the word counts behind it.
- **Location** ([Location](../../first-working-carl/spec.md#12-location)):
  - the Location switch on the Start screen: on the first time Carl is
    opened, then remembered on the phone;
  - `watchPosition` while the session runs, stopped while paused;
  - a fix sent first, then after a move of more than 500 m or when accuracy
    moves up a level;
  - reverse geocoding on the server with Nominatim: its own User-Agent,
    cached, at most 1 request a second, again only outside the last
    neighbourhood and at most once a minute;
  - worse than 1 km gives the town only, worse than 20 km gives no location;
  - off or denied gives the date, time and timezone only. A denial is noted
    once in the event log, and Carl doesn't ask again.
  - a geocoder failure keeps the last place name;
  - coordinates never go to any model;
  - the disclosure's location clause now follows the switch.
- **Cost metering** for decision calls from the price table. A call with
  unknown usage gets an estimate, marked as estimated
  ([Cost metering](../../first-working-carl/spec.md#11-cost-metering)).
- **Recording** ([What a recording keeps](../../first-working-carl/spec.md#what-a-recording-keeps)):
  - for each model call, the prompt's name and hash with the values filled
    in, the response, model id, parameters, token counts, response time and
    cost. A failed call records the typed error with the provider's full
    error text.
  - each candidate, repeat and card language;
  - every raw location fix, every geocoder response and the place context
    each call was given.
- **Prompt example cases and their runner** ([Testing prompts](../../first-working-carl/spec.md#testing-prompts)):
  - a few hand-written Finnish and English cases for `decision.md` under
    `prompts/examples/`;
  - a script that runs them against the configured model and prints the
    typed answers next to the expected ones;
  - run by hand, never in CI.

## Leaves working

Dinners that record what Carl would have checked.

## Done when

- [ ] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: the backchannel skip, the repeat and
      candidate thresholds, card language, the location accuracy cuts and
      the decision model's cost maths.
- [ ] The decision prompt's example cases have been run by hand against the
      configured model.
- [ ] Deployed and used for one recording session on the phone, at a real
      dinner or with a Finnish radio talk show playing beside it. Its event
      log shows the candidates and repeats Carl found.
