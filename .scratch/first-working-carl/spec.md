# First working Carl: spec

This spec was assembled on 2026-09-26 from the 25 resolved tickets of the
[First working Carl map](map.md). It is written for whoever builds the first
working version and hasn't read the tickets. It collects what the tickets
decided and adds no decisions of its own.

- The [product spec][product] sets how Carl behaves and still applies. This
  spec says what the first version builds and how. Any behaviour it doesn't
  repeat comes from the product spec.
- Terms in **bold** are defined in [`CONTEXT.md`][context]. Use them exactly.
- Each section ends with the tickets it comes from. The reasoning and the
  rejected options are in those tickets.
- Where tickets differ, the later decision wins and only that one appears
  here. If a ticket disagrees with this spec, follow this spec.

## Contents

1. [Purpose and scope](#1-purpose-and-scope)
2. [Architecture](#2-architecture)
3. [The pipeline stage by stage](#3-the-pipeline-stage-by-stage)
4. [Audio and utterances](#4-audio-and-utterances)
5. [Decision, repeats and settling](#5-decision-repeats-and-settling)
6. [Fact-finding, fact-checking and confidence bands](#6-fact-finding-fact-checking-and-confidence-bands)
7. [Card language, prompts and the blocklist](#7-card-language-prompts-and-the-blocklist)
8. [The screen](#8-the-screen)
9. [Recording sessions, disclosure and the test corpus](#9-recording-sessions-disclosure-and-the-test-corpus)
10. [Failures and outages](#10-failures-and-outages)
11. [Cost metering](#11-cost-metering)
12. [Location](#12-location)
13. [Config file contents](#13-config-file-contents)
14. [Build order](#14-build-order)
15. [Next version](#15-next-version)
16. [Decided at arrival](#16-decided-at-arrival)

## 1. Purpose and scope

### What the first working version is

It is a web page, opened on the owner's phone, that runs Carl's whole
pipeline end to end:

```
mic → speech-to-text → decision → fact-finding → fact-checking → fact card on screen
```

Each stage runs a provisional model behind a provider-neutral interface, and
the model can be swapped through configuration. The version includes
development mode, so real dinners can be recorded as **recording sessions**.
These recordings start the **test corpus**.

- **Target device:** Android Chrome on the owner's phone. iOS Safari is
  best-effort only.
- **Development mode first.** Any **session** can be a recording session. A
  normal session runs the same pipeline with recording off.
- **Recording sessions show fact cards live,** exactly as the product spec
  describes, rather than logging them silently. **Check time**, the **table**
  settling a point and **late cards** can only be seen live, and the table has
  been told the session is a test.

### What "done" means

The first version is done when **one 2-hour session runs end to end on the
phone without breaking and is recorded completely**. "Completely" means every
speech-to-text event and every model call, each with its config, response time
and cost, with check time and cost measured. A gap caused by a dropped
connection still counts as recorded completely.

Done has no quality targets. The product spec's precision, recall, check-time
and cost targets are measured later, on the test corpus, in a separate
comparison effort.

### What the first version has

- The **Start screen**: Start, the "Record this session" and Location
  switches, the month's running cost and the last session's cost.
- The recording-session disclosure screen, the recording mark and the one-way
  "Stop recording?".
- The session screen:
  - the **top bar**, with the **listening indicator** (listening, paused,
    can't hear, can't check), the recording mark, **Pause**, and End, which
    asks for confirmation first;
  - one large fact card at a time, kept until someone taps it away, with its
    Claim/Question label and hedged mark;
  - the **card history**, into which late cards are filed;
  - card pacing.
- The screen kept on for the whole session.
- Location, with an off switch.
- The drop rule: a candidate the table **settles** before its card is on
  screen gets no card.
- One card per claim or open question per session, so a **repeat** gets
  nothing new.
- The **failure log**. It is written but can't be viewed yet.
- Cost metered from the start.
- A "Session ended" summary.
- The owner-only script, including turning a recording session into
  owner-correctable Markdown.

A session ends when anyone taps End, when the page is closed, or when the page
loses its connection for more than 2 minutes. Ending after 30 minutes without
an utterance comes in the [next version](#15-next-version).

### Out of scope

- **The full vendor and model comparison** against the test corpus: word error
  rate, speaker attribution, precision and recall per stage, and cost. It is a
  later, separate effort that uses the recordings this version makes.
- **A replay and scoring harness** for the test corpus. It belongs with that
  comparison. This version only records what a replay will need.
- **Self-hosted speech-to-text** (Parakeet v3, NVIDIA's Nemotron streaming
  ASR). The recorded audio lets the comparison replay it later.
- **Public-product concerns:** onboarding, billing, multi-tenant accounts.

Sources: [What "done" means for the first working version][t01],
[Provisional models for each stage][t07],
[Running Parakeet v3 for Carl's speech-to-text][t15], [Build order][t25], the
[map's Out of scope](map.md#out-of-scope).

## 2. Architecture

### Page and server

The page is thin. The whole pipeline runs on a server.

| The page does | The server does |
| --- | --- |
| Microphone capture and audio streaming | Speech-to-text, and splitting its final segments into utterances |
| The screen, including pacing cards and filing late cards | The decision model, the settle call, both fact-finding models and the fact-checking model |
| The wake lock | Excerpt matching, the blocklist, confidence bands, repeats and the drop rule |
| Location fixes (`watchPosition`) | Reverse geocoding |
| The Start, Pause, End and "Stop recording?" taps | Session state, including the state of every card |
| Buffering its own failures until it can send them | Cost metering, the failure log and recording |

- All provider keys and all swappable model interfaces live only on the
  server, speech-to-text included. A self-hosted model can later plug in behind
  the same interface. Audio takes one extra hop, tens of ms inside the EU.
- The page makes no third-party calls.
- **The server is the source of truth for the session's cards.** After a
  reconnect it sends the current card and the card history again, and the page
  rebuilds its screen.

### One WebSocket

A single WebSocket connects the page and the server.

- Binary frames carry audio.
- JSON text frames carry Start, Pause, End, the heartbeat, cards and the
  listening indicator's state.
- Both sides send a heartbeat every 3 s (config) when they have sent nothing
  else in that time. It keeps the link open through quiet stretches and Pause.
- A side that hears nothing from the other for 10 s (config) treats the
  connection as dropped (see [Can't hear](#cant-hear)).
- At session start the server sends the page the config values the page
  needs itself: the heartbeat and silence times, the pacing and late-card
  times, and the location thresholds.
- The browser sends its access-pass cookie on the WebSocket upgrade.
- **Speech-to-text always goes through the server,** even though most
  providers would let the browser connect directly with a short-lived token.
  Relaying works with every provider, self-hosted ones included. The recording,
  the reconnect grace period and Pause's finalise also need the audio and the
  stream on the server.

### Hosting

Carl follows the cloud setup of
[akaihola/drum-transcribe](https://github.com/akaihola/drum-transcribe) and
reuses its pieces. See its `docs/operations.md`, `docs/recovery.md`,
`docs/loading-page-plan.md` and the Throttling part of `docs/webapp.md`.

- **One Scaleway Serverless Container** in fr-par runs a Python server
  (asyncio and a WebSocket library, managed with `uv`) from a slim image.
  - It is **scaled to zero** when idle and has **max scale 1**, so every
    connection of a session reaches the same instance.
  - It serves both the page and the WebSocket.
- **The address is `faktat.vempai.men`.** It is a CNAME in the Cloudflare
  `vempai.men` zone, proxied, pointing at the container endpoint. The zone's
  SSL setting is "Full", and Scaleway keeps its own certificate for the
  domain.
- **A loading page sits in front.**
  - It is a copy of drum-transcribe's Cloudflare Worker
    (`deploy/cloudflare/worker.js`, free plan) on the route
    `faktat.vempai.men/*`. If the Worker fails, requests go straight through.
  - When the container doesn't answer a page load within 2.5 s, the Worker
    shows a "Starting up…" page with a seconds counter. It polls a cheap
    endpoint with no side effects and reloads once the container is up.
  - A second route, `faktat.vempai.men/api/*`, has no Worker. The session
    WebSocket, the health poll and all API calls go straight through
    Cloudflare's proxy.
  - To switch the loading page off, set the DNS record back to "DNS only".
- **Scaleway ends every request after 60 minutes.** A WebSocket is taken to be
  a request too. At about 50 minutes the page therefore opens a second
  WebSocket, moves the audio onto it and closes the old one. Nothing is lost,
  and the server's speech-to-text stream stays open. Build step 1 measures the
  real limit.
- **Fallback:** if the handover proves unworkable, or the container's CPU is
  throttled while no page is connected, Carl moves to a Scaleway Instance
  (always on, about €3.50 a month) running the same container image.

### Access passes

- The whole site is behind an **access pass**: page, WebSocket, API and admin
  routes. Only the health endpoint and the loading page are open.
- The owner can issue several passes. Each is a scrypt entry (`salt:hash`) in
  the `CARL_PASSWORDS` secret variable.
- A `hash-password` command makes an entry. It can also generate a four-word
  passphrase (about 72 bits).
- A correct pass sets a stateless cookie, `HMAC(TOKEN_SECRET, salt of that
  entry)`, with HttpOnly, Secure and SameSite=Lax, valid for 1 year.
- Deleting an entry revokes that pass's cookies. Rotating `TOKEN_SECRET`
  revokes all of them.
- A wrong pass is answered after a 1 s wait. There is no lockout.
- Any access pass may start a recording session. All passes belong to the
  owner's own browsers.

### Secrets

- The container's **secret environment variables** hold all provider keys,
  the bucket key, `CARL_PASSWORDS` and `TOKEN_SECRET`. Scaleway replaces the
  whole set on every update, so they are always set together in one update.
- Locally, they live in gitignored `.secrets.*` files at the repo root.
- Each of them is also copied into the owner's password manager, together with
  the Scaleway and Cloudflare API credentials. The Cloudflare credential is
  `.secrets.cloudflare.env`, a Workers token limited to the zone.
- A recovery doc lists them all, as drum-transcribe's `recovery.md` does.
  `TOKEN_SECRET` can't be recreated without logging every browser out.
- Nothing secret goes into the page, the image or the repo.
- A **hard monthly spend limit** is set in every provider dashboard that
  offers one. It is the backstop while the **monthly budget** waits for the
  next version.

### Storage

One Scaleway Object Storage bucket in fr-par holds everything the server keeps.
The server reaches it with a scoped IAM-application key that covers object
storage only and has an expiry date.

| Prefix | Holds | Kept |
| --- | --- | --- |
| `recordings/<id>/` | A recording session's raw audio chunks and JSONL event log, plus the config, prompts and commit it ran with | 180 days (lifecycle rule) |
| `corpus/<id>.md` | A recording session's owner-corrected Markdown | Until the owner deletes it |
| `sessions/<id>/state.json` | Session state, used to resume after a restart | Deleted at End. A 1-day lifecycle rule removes any left behind |
| `failures/` | The failure log | 30 days (lifecycle rule) |
| `costs/` | One cost summary per session, and one month-to-date object | Indefinitely |

- Lifecycle rules run daily and can act up to 24 h late.
- `recordings/` has no versioning and no backups, so expired or deleted
  material is really gone.
- Local runs write under a `dev/` prefix in the same bucket.
- Data is encrypted at rest only by the provider's default, and only the owner
  has access. The server needs plaintext for replays.
- The single instance rewrites the objects in `costs/`.

On the phone, the page keeps the Location switch setting, any recording stop
that hasn't reached the server yet (see
[Stopping a recording](#stopping-a-recording)), and its access-pass cookie.
Recordings are never kept on the phone.

### Deploys and the config file

- There is one cloud deploy, done by hand:
  1. `docker build`;
  2. push to the Scaleway registry;
  3. `scw container redeploy`;
  4. deploy the Worker with `npx wrangler deploy`.
- Never deploy during a dinner: a redeploy drops live sessions.
- Staging is the same server run locally, writing under `dev/`.
- Development mode is not a separate deploy. It is the "Record this session"
  switch.
- The **config file** (see [Config file contents](#13-config-file-contents))
  and the prompt files under `prompts/` are committed and baked into the
  image. Changing either means a redeploy.

### The page

- Plain HTML, CSS and JS modules, with no build step and no framework, served
  by the Python server.
- The AudioWorklet is its own small JS file.
- The Atkinson Hyperlegible font is self-hosted.

### The owner-only script

The owner runs it from their own computer. It uses the bucket key directly, so
the server needs no admin route.

| Command | What it does |
| --- | --- |
| `list` | Lists recording sessions by date, time and duration |
| `export <id>` | Downloads everything kept for a session, to answer an access request: the audio joined into one WAV file, the event log, and the corpus Markdown if there is one |
| `fetch <id>` | Downloads `corpus/<id>.md`, to correct it |
| `delete <id>` | Removes `recordings/<id>/` and `corpus/<id>.md` |
| `generate <id>` | Writes `corpus/<id>.md` from the recording's event log |
| `put <file>` | Runs `check`, then uploads over `corpus/<id>.md` |
| `check` | Validates a corrected corpus file |
| month totals | Prints month totals per provider from `costs/`, to compare with the providers' dashboards |

Sources: [What runs in the browser and what runs on a server][t06],
[How audio is streamed and how speaker labels reach the decision model][t08],
[Hosting and secrets][t13], [ADR 0002][adr2],
[Where the card archive, failure log and recording sessions are kept][t11],
[Metering running cost against the monthly budget][t12],
[Turning a recording session into owner-correctable Markdown][t14],
[Development mode and the recording-session disclosure][t21],
[Location in the pipeline and the test corpus][t20], [Build order][t25],
[Scaleway as Carl's host][t16].

## 3. The pipeline stage by stage

### Shape

```
mic ─► speech-to-text ─► utterance ─┬─► decision call ─► candidate?
                                    └─► settle call (while any candidate is live)

candidate ─┬─► fact-finder A ─┐   in parallel
           └─► fact-finder B ─┘
                     │
                     ▼
     match excerpts, check the blocklist
     a verdict per draft card, plus the agreement call    (fact-checking model)
                     │
                     ▼
     band: plain, hedged or nothing ─► card to the page ─► screen or card history
```

- **There is no message-writing stage.** The **fact-finding models** search the
  web and write the **draft card** themselves. The **fact-checking model**
  judges each draft card against its source excerpt.
- **The decision model and the fact-checking model give typed answers only**
  and never write text. Classifier-style models such as TypeSafe Jev therefore
  fit, and nothing a judging model writes can reach the screen unchecked
  ([ADR 0001][adr1]).
- Two fact-finding models run on every candidate. This spec calls them
  **fact-finder A** and **fact-finder B**.

### Stage interfaces

Every interface is provider-neutral. Each sits behind an adapter that the
config file selects.

**Speech-to-text**

- `open(languages [fi, en], audio format)` returns a stream of interim and
  final events. Each word carries a **speaker label**, a start time, an end
  time and a language code. The card language is counted from these codes.
  An adapter for a provider that transcribes one language per stream tags
  every word with that stream's language.
- `close()` ends the stream.
- Splitting final segments into utterances happens in the pipeline, not in the
  adapter.

**The typed-answer interface.** The decision and settle calls, the verdicts and
the agreement call all share it.

- Input: named text fields, one question, and an answer type. The answer type
  is a choice from a list given in the input, a boolean, or a score in a
  stated range.
- Output: the answer and a probability for each choice, or for true and false.
  - LLM adapters use a JSON schema that allows only the given choices.
  - Probabilities come from logprobs where the vendor has them. Otherwise
    they are empty.

| Call | Model | Judges | Choices |
| --- | --- | --- | --- |
| Decision call | Decision model | The new utterance | `none / claim / open question / same as C1 … Cn` |
| Settle call | Decision model | The new utterance | `none`; `settles Cn` for a live candidate not yet on screen; `agrees with Cn / disputes Cn` for the one on screen |
| Verdict | Fact-checking model | One draft card | `supported / not supported / doesn't answer the candidate` |
| Agreement call | Fact-checking model | Two draft cards with the same outcome | `same fact / compatible but different / contradict` |

What each call is given is set out in sections [5](#5-decision-repeats-and-settling)
and [6](#6-fact-finding-fact-checking-and-confidence-bands).

**Fact-finding model**

- Input: the candidate, its context, the date, time and place, and the
  **card language**.
- Output:
  - an outcome: `claim is wrong / claim is right / question answered / not
    found`;
  - the candidate restated as one standalone sentence ("Who played Rick in
    *Casablanca*?"). It is returned for every outcome, silent ones included;
  - for `claim is wrong` and `question answered` only, a draft card: a title, a
    one-sentence fact, the source's URL and title, and a verbatim excerpt from
    the source that supports the fact.
- `claim is right` and `not found` end the candidate silently.

**Every call** also returns the model id, prompt version, parameters, token
counts, cost and response time. On failure it returns a typed error instead:
`timeout`, `unavailable`, `rate-limited` or `bad output`. Adapters never retry.
The pipeline decides what to do with each error and writes it to the failure
log.

### Provisional models

| Stage | Provisional model | Fallback |
| --- | --- | --- |
| Speech-to-text | Soniox stt-rt-v5 (about $0.12/h) | AssemblyAI Universal-3.6 Pro Streaming, tried in the comparison |
| Decision model (decision and settle calls) | GPT-6 Luna, typed JSON schema, reasoning off (about $0.06/h) | TypeSafe Jev, tried in the comparison |
| Fact-finder A | GPT-6 Luna with OpenAI web search: Responses API, reasoning effort `none`, `tool_choice: "required"`, JSON output | Luna on Perplexity's Agent API |
| Fact-finder B | Perplexity's Agent API with the model pinned to `gemini-3.8-flash`, Perplexity's `web_search` ($2.50 per 1,000 searches) and a JSON schema | Another non-OpenAI model on Perplexity's Agent API with its `web_search`. As a stopgap, fact-finder A alone, which allows hedged cards only |
| Fact-checking model (verdicts and agreement call) | TypeSafe Jev, pinned as `typesafe/jev-1.13` through OpenRouter | Gemini 3.5 Flash-Lite, typed, with logprobs, called directly without grounding |

- Build step 0 either confirms each text stage's provisional model or picks its
  fallback.
- The two fact-finders run in parallel on every candidate. They use different
  model vendors (OpenAI and Google) and different search engines (OpenAI and
  Perplexity).
- Fact-finder B's model is pinned so that Perplexity's `fast` preset can't
  change the model under Carl.
- Jev goes through OpenRouter's `/api/v1/systemone`, which takes TypeSafe's
  own request format and is served by TypeSafe at TypeSafe's price. Its
  `~typesafe/jev-latest` alias is not used, since it could change the model
  under Carl. Requests there are limited to 32k tokens.
- Calls to OpenAI send `store: false`.
- **No Anthropic models:** the owner's subscription can't be used for API
  calls.
- **No Google Search grounding:** its terms forbid storing and analysing
  grounded results, and recording sessions do both. Gemini through Perplexity's
  search, and plain Gemini without grounding, don't produce grounded results.
- **Estimated running cost:** about $0.35–0.55 an hour at 10–20 candidates an
  hour. That is $0.12 for speech-to-text, $0.06 for the decision model,
  $0.11–0.22 for fact-finder A, $0.06–0.12 for fact-finder B, and under a cent
  for fact-checking.

### Swapping a model

- The config file maps each stage to its provider, model and parameters. The
  keys are server secrets.
- A change means a redeploy.
- Each recording session stores the config it ran with, so a replay knows what
  ran.
- Switching models at runtime belongs to the comparison effort.

Sources: [Provisional models for each stage][t07], [ADR 0001][adr1],
[Decision model context and candidate de-duplication][t09],
[Tracking a candidate until its card][t18],
[Splitting verdict confidence into plain, hedged and silent][t10],
[Search providers' terms and Luna web search][t17], [Build order][t25],
[Streaming speech-to-text for Finnish and English table audio][t02],
[Models for the decision, fact-checking and message-writing stages][t03].

## 4. Audio and utterances

### From the microphone to the server

- An AudioWorklet (`AudioContext({sampleRate: 16000})`) produces raw 16 kHz
  16-bit mono PCM.
- The page sends it in chunks of about 100 ms, about 115 MB an hour, which is
  fine on home wifi.
- Each chunk stands alone, so reconnects and Pause need no container headers.
  The server passes the bytes to Soniox unchanged (`s16le`).
- `echoCancellation` and `noiseSuppression` are off, and `autoGainControl` is
  on. The page reads back `track.getSettings()`, and each recording session
  stores the result.
- The page holds a Screen Wake Lock for the whole session.
  - iOS mutes the microphone whenever the page is hidden.
  - Android Chrome probably keeps capturing in the background, behind a
    microphone notification, but this isn't guaranteed.
- The documentation tells the owner that a long session needs a charger.

### The speech-to-text stream

- **Settings:** Soniox endpoint detection is on, with `max_endpoint_delay_ms`
  starting at 1,500 ms (config), and `language_hints: [fi, en]`.
- **When the page drops:** the server keeps the Soniox stream open with
  keepalives through the 2-minute reconnect grace period, at a cost of at most
  about $0.004. Speaker labels therefore carry on after a short drop.
- **When Soniox drops:** the server opens a new stream at once, backing off 1,
  2, 4… up to 30 s. Meanwhile the listening indicator shows "Can't hear" and the
  failure log records the gap.
- **Rotation:** a stream nearing Soniox's 300-minute limit is replaced at the
  next segment end.
- **Pause:**
  - The page stops the microphone track, so the phone's own microphone
    indicator goes off, and tells the server.
  - The server sends Soniox's manual finalise, so words spoken before the tap
    become final and are processed normally. It then closes the stream, and
    opens a new one when the session resumes.
  - Pause acts from the tap forward. Checks that started before Pause finish,
    and their cards are shown.
  - The heartbeat keeps the page–server link open while paused.

### From final segments to utterances

- A final segment is split wherever the speaker label changes.
- A run of 2 words or fewer between two runs by the same speaker is treated as
  a false switch and merged into them.
- An utterance longer than about 30 s is split at the next sentence end, so the
  decision model never waits for a monologue to end.
- Overlapping speech gets no special handling.
- The recording keeps Soniox's raw tokens and labels, so corrections and
  replays see what speech-to-text actually heard.

### Speaker labels

- A speaker label is only valid within its own stream. Every new stream gets
  fresh labels (for example B1, B2…): after Pause, a Soniox drop, a server
  restart or a rotation.
- At each stream boundary, the decision context gets a "(paused)" or "(gap)"
  marker.
- Carl doesn't match voices across streams. The owner merges labels by hand in
  the test corpus.

Sources: [How audio is streamed and how speaker labels reach the decision model][t08],
[What runs in the browser and what runs on a server][t06],
[What a phone browser allows a web page to do][t04], [product spec][product].

## 5. Decision, repeats and settling

### When the decision call runs

- **On every utterance.** Each call runs to the end. A newer utterance never
  cancels an unfinished call, so a claim followed at once by "Oh really?" is
  still judged.
- **Skipped:** only utterances made up entirely of words from a fixed Finnish
  and English list of backchannel and filler words (joo, niin, aha, mm, jaa,
  okei, yeah, right, uh-huh, wow…).
  - There is no minimum word count, because short open questions ("Kuka se
    oli?", "'53 vai '54?") must reach the model.
  - Skipped utterances still appear in the context of later calls.

### What the decision call is given

- The new utterance, marked as the one being judged.
- Up to the **10 preceding utterances from no more than the last 2 minutes**
  (config). Only earlier speech, never later.
- Speaker labels and the "(paused)" and "(gap)" markers.
- The place name (neighbourhood, city, country) with the local date, time and
  timezone (see [Location](#12-location)).
- **The session's earlier candidates,** listed by Carl's own ids (C1, C2…).
  - The list covers the whole session, across Pauses and gaps, with no cap. A
    2-hour session has about 20–40, a few hundred tokens.
  - Each is shown by its standalone restatement. The first restatement to
    arrive from the two fact-finders is used, and the recording keeps both.
    Until one arrives, the raw utterance is shown.
- The prompt tells the model to answer `none` when the subject of a claim
  can't be worked out from the window.

### From probabilities to an outcome

1. If the `same as` choices together reach **0.5**, the utterance is a
   **repeat** of the most likely one.
2. Otherwise, if `claim` and `open question` together reach the **candidate
   threshold** (starting at 0.5), the utterance is a candidate of whichever
   kind is more likely.
3. Otherwise the outcome is `none`.

If the vendor returns no probabilities (no logprobs), Carl takes the chosen
answer as it is. Both thresholds are in the config file.

### Repeats

- **The same** means asserting the same thing or asking the same question, in
  any language or wording. The same topic isn't enough.
  - "He did fail maths, though" repeats "Einstein failed maths".
  - "He failed physics, actually" is a new claim.
  - "It was '52, wasn't it?" after "1953 or '54?" is a new claim about the
    same question. A false answer from the table is therefore still checked.
- A repeat gets nothing new if the earlier candidate:
  - got a card, which stays in the card history;
  - ended silently: the claim was right, nothing was found, it fell below the
    hedged band, or it was settled;
  - is still being checked.
- A repeat of a candidate that **failed at a stage** is checked as a new
  candidate, since nothing was decided. Failing covers any typed error, the
  60 s candidate timeout and `overload`.
- Each recorded repeat links to the candidate it matched, with its
  probability.

### The settle call

- While at least one candidate is **live**, each utterance also gets a small
  typed **settle call**, alongside the decision call. Live means being
  checked, waiting for the screen, or on screen.
- It uses the same model and the same context window as the decision call, but
  gets only the date and time, with no place.
- It lists only the live candidates, each by its standalone restatement. An
  on-screen candidate also shows its card's fact.
- Choices:
  - `none`;
  - `settles Cn` for a candidate that isn't on screen yet;
  - `agrees with Cn` or `disputes Cn` for the candidate on screen.
- A choice counts from a probability of 0.5 (config).
- It waits until the decision on every earlier utterance is known, so a
  candidate flagged two seconds earlier isn't missed.
- The candidate's own speaker correcting themselves settles it. "Let's look it
  up" and "I'm not sure" don't.

### What a settle does

- **Before the card is on screen,** the candidate is dropped:
  - its checks are cancelled, or their results thrown away;
  - a card already sent to the page is withdrawn;
  - the recording keeps `silent:settled` with the settling utterance's id.
- **The settling utterance** goes through the decision call like any other,
  and a claim in it gets its own check. A right correction therefore ends
  silently, while a false one, or a wrong answer to an open question, gets its
  own card.
- **On screen:**
  - `agrees` marks the card "Settled at the table". The mark never appears when
    the table got it wrong.
  - `disputes` adds no mark. The disputing utterance isn't checked
    separately, because the card on screen already answers it.
- A card in the card history never changes.
- **The first version builds the whole settle call,** `agrees` and `disputes`
  included. `agrees` is recorded but shows nothing until the next version adds
  the "Settled at the table" mark.

### Candidates run side by side

- There is no queue. Each candidate is its own independent task on the server,
  with its own state: finding → checking → ready → on screen, card history,
  silent, dropped or failed.
- At most **8 candidates** can be live at once (config). Beyond that, a new
  candidate fails with an `overload` entry in the failure log, so a repeat of
  it is checked later.
- A candidate that hasn't finished **60 s** after its utterance has failed
  (config).

Sources: [Decision model context and candidate de-duplication][t09],
[Tracking a candidate until its card][t18],
[Location in the pipeline and the test corpus][t20],
[The can't-hear-or-check state and the failure log][t22], [Build order][t25].

## 6. Fact-finding, fact-checking and confidence bands

Carl's confidence comes from **agreement** between the two fact-finding models,
plus Carl's own **verified excerpt**. It never comes from a model's
self-reported confidence.

### Fact-finding

- Both fact-finders get the same prompt (`prompts/fact-finding.md`) and the
  same input:
  - the candidate utterance and the decision call's context window;
  - the place name with the local date, time and timezone;
  - the card language.
- Each search tool is also told where the table is, as place names and never
  as coordinates (see [Location](#12-location)).
- The search language isn't steered: the fact-finders search wherever the best
  source is.
- Each writes its draft card's title and one-sentence fact in the card
  language. The excerpt stays word for word in the source's own language.
- The restatement must name any place the card depends on.
- The prompt asks them to prefer primary sources (official bodies, statistics
  offices, the original publication) or reference works (encyclopedias
  including Wikipedia, dictionaries, major news outlets). It tells them never
  to cite forums, social media or video.

### Waiting for both

- Carl waits for both fact-finders' outcomes until **about 12 s after the first
  arrives** (config).
- A fact-finder that fails or misses that deadline leaves the other's card to
  be judged alone.
- A card is never shown first and then confirmed or withdrawn later.

### Matching excerpts against their sources

- **Fact-finder B (Perplexity):** the excerpt must be a substring of a
  `search_results` snippet from the same URL.
- **Fact-finder A (OpenAI):** OpenAI's `url_citation` carries no source text.
  The server therefore downloads the source URL (timeout about 3 s, config)
  and looks for the excerpt after normalising whitespace and quotation marks.
- A match makes the excerpt a **verified excerpt**. A failed download or a
  miss leaves the card unverified. Neither goes into the failure log.

### The blocklist

- The blocklist is a list of domain suffixes in the config file. `reddit.com`
  also blocks `old.reddit.com`.
- It covers forums and Q&A sites such as Reddit and Quora, social media, video
  platforms, and user-edited wikis other than Wikipedia.
- Carl checks each draft card's source URL against it after the fact-finders
  return. A blocklisted source counts as no citable source.
- The list is never put in a prompt.
- There is no allowlist, since one would silence situational questions.

### Verdicts and the agreement call

- **A verdict for each draft card.** The fact-checking model judges each draft
  card separately: `supported`, `not supported` or `doesn't answer the
  candidate`.
  - It gets the original candidate utterance with its context window, the draft
    card, its source excerpt, and the date and time.
  - It never gets the fact-finders' restatements, so a fact-finder's misreading
    can't vouch for itself.
- **The agreement call** runs when both fact-finders return the same outcome:
  both `claim is wrong` or both `question answered`.
  - It is one more typed call to the fact-checking model, alongside the
    verdicts, given the candidate and both cards.
  - `same fact` means agreement.
  - `compatible but different` means no agreement, and each card is judged
    alone.
  - `contradict` (1954 against 1955) means nothing is shown.
- Some outcome pairs need no agreement call:
  - `claim is wrong` against `claim is right` is a contradiction.
  - `claim is wrong` or `question answered` against `not found`, or against a
    failed fact-finder, leaves the one card to be judged alone.
- Both calls judge the card and excerpt as they are, even when they are in
  different languages, and their prompts say so. Nothing is translated.

### The bands

The starting thresholds below are in the config file.

| Band | Needs |
| --- | --- |
| **Plain fact card** | Agreement with p(same fact) ≥ 0.7. The shown card has a verified excerpt, a source that isn't blocklisted, and p(supported) ≥ 0.85. The other card has p(supported) ≥ 0.5 |
| **Hedged fact card** | One card with a verified excerpt, a source that isn't blocklisted and p(supported) ≥ 0.6, and no contradiction from the other fact-finder. This covers a card from a single fact-finder and an agreeing pair that falls short of the plain bar |
| **Nothing** | Everything else, and any contradiction |

- **Every card shown has at least one verified excerpt behind it.** An
  unverified card can only be the second card of an agreeing pair.
- **Which card is shown:** the verified one. If both are verified, the one with
  the higher p(supported) is shown.
- **No probabilities:** if the fact-checking model gives no logprobs,
  `supported` meets only the hedged threshold. The card is then hedged at best,
  even with agreement.
- **No categories are held back or capped,** such as health or time-sensitive
  facts. The product spec rules out refusing by category.
- While only one fact-finder is working, only hedged cards are possible.

### The hedge

- There is one hedge level. A fixed word goes before the checked sentence:
  "Todennäköisesti: …" or "Probably: …", in the card language.
- The sentence itself stays exactly as it was judged.
- The card also carries a visual mark (see [The screen](#8-the-screen)).
- Carl adds the prefix itself; no model writes it. The product spec's "maybe"
  isn't used.

### Reason codes

Each band is recorded with a reason code, for example `plain:agreed`,
`hedged:single-verified`, `silent:contradiction`, `silent:unverified` or
`silent:settled`. With these, the comparison can tune thresholds without
replaying the calls.

Sources: [Splitting verdict confidence into plain, hedged and silent][t10],
[Provisional models for each stage][t07],
[Decision model context and candidate de-duplication][t09],
[Search providers' terms and Luna web search][t17],
[Location in the pipeline and the test corpus][t20],
[Prompts, card language and the source blocklist][t23],
[Tracking a candidate until its card][t18], [ADR 0001][adr1].

## 7. Card language, prompts and the blocklist

### Card language

- The **card language** is the language with the most words over the last
  **10 minutes** of final utterances. Carl counts words by the language code
  each word carries (Soniox tags every token). Carl works it out itself; no
  model decides it.
- If that window holds fewer than **about 50 words**, or the count is a tie,
  the candidate utterance's own language is used.
- There is no setting for it. The window and the word minimum are in the
  config file.
- Each candidate's events record the chosen language and the word counts behind
  it.
- Example: at a Finnish dinner, someone quotes a wrong line from an English
  song. The card is in Finnish.

### What is written in which language

| Text | Language | Written by |
| --- | --- | --- |
| The card's title and one-sentence fact | Card language | The fact-finders |
| The source excerpt | The source's own, word for word | The source |
| The Claim/Question label: Väite or Claim, Kysymys or Question | Card language | Carl |
| The hedge prefix: "Todennäköisesti:" or "Probably:" | Card language | Carl |
| The hedged tag: "Varauksin" or "Hedged" | Card language | Carl |
| The settled mark: "Ratkesi pöydässä" or "Settled at the table" (next version) | Card language | Carl |
| Everything else Carl shows: top bar, listening indicator, buttons, Start screen, dialogs, the Log | English | Carl |
| The recording disclosure | Finnish, with English below | Carl |
| The prompts | English, naming the language to write in | – |

### Prompts: one source of truth

- There is one file per prompt: `prompts/decision.md`, `prompts/settle.md`,
  `prompts/fact-finding.md`, `prompts/fact-checking.md` and
  `prompts/same-fact.md` (the agreement call).
  - Each has `{placeholders}` that the server fills in.
  - Prompts belong to the pipeline, not to an adapter, so both fact-finders
    get the same text.
- No prompt text exists anywhere else, neither in code nor in the config file.
- The prompt files are committed and baked into the image with the config.
- Startup fails if a template has a placeholder that nothing fills.
- **Versioning:**
  - A prompt's version is a short content hash of its file.
  - At session start, a recording stores a copy of the config file and of
    every prompt file, next to the build's git commit.
  - Each model call's event records the prompt's name and hash and the values
    filled in, not the rendered text. A replay rebuilds the exact prompt from
    these.

### The blocklist and source preference

The blocklist and the prompt line asking for primary or reference sources are
described in
[Fact-finding, fact-checking and confidence bands](#6-fact-finding-fact-checking-and-confidence-bands).

### Testing prompts

- Each prompt has a few hand-written example cases, each in Finnish and in
  English, under `prompts/examples/`.
- A script runs them against the configured models and prints the typed answers
  next to the expected ones.
- It is run by hand after a prompt change, not in CI, because it costs money
  and needs the network. Its results aren't stored.
- Real test-corpus cases replace these examples in the comparison.

Sources: [Prompts, card language and the source blocklist][t23],
[Splitting verdict confidence into plain, hedged and silent][t10],
[The screen][t24].

## 8. The screen

The [screen prototype](prototypes/the-screen/screen-prototype.html) shows the
chosen layouts: P for portrait and L1 for landscape, in round 2. The rules below
are what was decided. The prototype's details aren't a specification.

### Overall

- Carl follows the phone into portrait or landscape. Landscape is the main
  case, because most phone cases hold the phone upright only sideways.
- The screen is dark whatever the phone's theme, and uses Atkinson
  Hyperlegible.
- It is readable across the table, 0.5–2 m away.
- Carl's own words are in English, and cards are in the card language (see the
  [table in section 7](#what-is-written-in-which-language)).

### The Start screen

- A big round Start button. In landscape, Start is on the left and everything
  else on the right. In portrait, everything else is below it.
- Switches:
  - "Record this session", off by default every time (see
    [section 9](#9-recording-sessions-disclosure-and-the-test-corpus));
  - Location, on the first time Carl is opened and then remembered on the
    phone.
- "This month ≈ €…", and the last session's date, length, cost and €/h.
- Nothing is heard before Start is tapped.
- With recording on, Start opens the disclosure screen first.

### The session screen

- **The top bar** is one row: the listening indicator, the recording mark,
  then Pause and End at the right end. The ⋯ menu joins them in the next
  version, when it has something to hold.
- **The listening indicator** is a pill:
  - green "Listening", with a pulsing dot while someone speaks;
  - amber "Paused";
  - striped orange "Can't hear" or "Can't check" (see
    [Failures and outages](#10-failures-and-outages)).
- **The recording mark** is a separate red "Recording" pill next to the
  indicator. It shows only while audio is actually being written. Tapping it
  opens "Stop recording?".
- **Pause** takes one tap from anyone, and another tap resumes.
- **End asks first.** Tapping End turns the top bar into "End the session?
  Cancel / End". A plain tap or click confirms, so it works with a touchpad or
  mouse too. Anyone at the table may end the session.
- **The current card** takes the rest of the screen and shows:
  - the coloured Claim/Question label;
  - for a **hedged fact card**, a "Varauksin" / "Hedged" tag next to the
    label, and the hedge prefix before the fact;
  - the title (the claim's gist in a few words);
  - the one-sentence fact;
  - the source, as a clearly visible, clickable link, which OpenAI's terms
    require of a citation that is shown.

  Tapping the source opens it in a new tab and leaves the card where it is.
  Tapping anywhere else on the card moves on. Opening a source hides Carl's
  page, which counts as losing the microphone until the page is back (see
  [Can't hear](#cant-hear)). When another card is waiting, "+N waiting" and a
  shrinking 8 s bar show under the card.
- **The card history** is always visible and scrollable, in small type.
  - In landscape it is a column on the right, about 30% of the width. In
    portrait it is a strip along the bottom, about 30% of the height.
  - Each card is a row, newest on top by utterance time, with older rows
    dimmer.
  - A claim is marked ≠ and a question ?. A hedged card has a dashed edge.
  - Each row's source is a link too, opened the same way.
  - A card that has been tapped away joins the card history.
- Between cards, only the top bar and the card history are on screen.

### Pacing and late cards

- The page paces the cards, since the taps happen there. The server holds each
  card's state and sends it again after a reconnect.
- With no other card waiting, the current card stays until someone taps it
  away.
- With another card waiting, the current card stays at least **8 s** (config),
  and a tap moves on at once.
- Waiting cards are shown in utterance order.
- A card that can't reach the screen within **20 s** of its utterance, measured
  at the moment it would reach the screen, is a **late card**.
  - It skips the screen and goes straight into the card history, at its place
    by utterance time, with no special mark.
  - This covers a card that was ready too late, one that waited behind
    another, and one that became ready while the connection was down.
- The server sends each card with its utterance time.
- The page reports back when each card was shown or filed, so the recording
  holds the true check time.

### After the session

A "Session ended" summary shows the listening time, the cards, the cost and
whether the recording was kept. It leads back to the Start screen.

### Placed now, built in the next version

- The "Settled at the table" mark, under the current card.
- The **live transcript line**. In landscape it sits in the top bar between the
  indicator and the controls. In portrait it sits under the current card. Its
  switch goes on the Start screen.
- The **card archive** and the Log, as small links in the Start screen's top
  corners.
  - The card archive is a list of sessions, with Wrong/Pointless marks and a
    note of missed moments.
  - The Log lists entries and outages, with a Clear that asks first.
- The ⋯ menu in the top bar, holding the transcript-line switch and the Log,
  as in the prototype.

Sources: [The screen][t24], [Tracking a candidate until its card][t18],
[Development mode and the recording-session disclosure][t21],
[The can't-hear-or-check state and the failure log][t22],
[What runs in the browser and what runs on a server][t06],
[Search providers' terms and Luna web search][t17],
[What "done" means for the first working version][t01],
[product spec][product].

## 9. Recording sessions, disclosure and the test corpus

### Starting one

- The Start screen has a "Record this session" switch. It is **off by default
  every time** and fixed at Start; the only change after that is the one-way
  stop below. Development mode is nothing more than this switch.
- Any access pass may start a recording session. Only the owner's bucket script
  reads recordings.
- With the switch on, Start opens a **disclosure screen**.
  - It shows the line for the owner to read aloud, in Finnish with English
    below.
  - It offers "Everyone agreed, start recording", "Start without recording" and
    Back.
  - It must be confirmed every time. There is no "don't show again".
  - The event log records the confirmation and the exact text shown.
- Carl makes no announcement of its own.

### The disclosure text

> **FI:** Tämä on testi. Carl tallentaa keskustelun äänen ja tekstin sekä
> puhelimen sijainnin. Ääni ja raakalokit poistuvat 6 kuukauden kuluttua;
> korjattu teksti ilman nimiä säilyy siihen asti, kunnes poistan sen. Vain minä
> ja testattavat tekoälypalvelut käsittelevät niitä. Kuka tahansa voi pyytää
> lopettamaan tallennuksen.
>
> **EN:** This is a test. Carl records the conversation's audio and text and
> the phone's location. Audio and raw logs are deleted after 6 months; the
> corrected text, without names, stays until I delete it. Only I and the AI
> services being tested handle them. Anyone can ask to stop the recording.

With location off, the location clause ("sekä puhelimen sijainnin" / "and the
phone's location") is left out.

For a normal session, the owner tells the table in their own words. The product
spec's suggested line says that the conversation goes to cloud AI services, and
so does the phone's location unless it is switched off.

### The recording mark

- A red "Recording" pill, shown **whenever audio is actually being written**.
  It sits next to whatever state the listening indicator shows and is not a
  state of its own.
- Pause hides it, since nothing is heard or kept, and resuming brings it back.
- In the can't-hear and can't-check states it shows only if audio still reaches
  storage.
- After a stop it is gone for good.

### Stopping a recording

- Anyone may object. Tapping the recording mark opens "Stop recording?".
- Confirming turns the session into a normal session from that moment. It
  **deletes everything recorded so far, at once**: all of `recordings/<id>/`.
  No corpus file is ever made.
- The stop is one-way. Recording again means End and a fresh Start with a fresh
  disclosure. To leave out just the next part of the conversation, use Pause.
- A stop leaves only the session's cost summary, which has no conversation
  content, with one line: "recording stopped and deleted at hh:mm". A stop is
  not a failure, so the failure log gets nothing.
- **A stop made while the connection is down is never lost.**
  - The mark goes off on the page at once.
  - The page sends the stop again on reconnect. If the session ends first, the
    page keeps the stop in local storage and sends it the next time Carl opens.
  - The server applies the stop whenever it arrives. No audio reaches the
    server meanwhile, so nothing new is recorded.

### What a recording keeps

Everything goes under `recordings/<id>/` and is written while the session
runs, not at End.

- **Audio:** raw 16 kHz 16-bit PCM exactly as it was sent to speech-to-text,
  about 230 MB per 2 hours, in objects of roughly one minute each.
- **A JSONL event log,** flushed about every 10 s. A crash loses at most one
  audio chunk and a few seconds of log. It holds:
  - **at session start:** the config file, every prompt file, the build's git
    commit, the microphone settings, and the disclosure confirmation with its
    text;
  - **speech-to-text:** every event with its timestamps, interim ones included,
    with Soniox's raw tokens, speaker labels and language tags;
  - **model calls:** for each call, the prompt's name and hash with the values
    filled in, the response, the model id, parameters, token counts, response
    time and cost. Cost includes Carl's figure, the provider's when it gives
    one, and whether it is estimated. A failed call records the typed error
    with the provider's full error text;
  - **source-page downloads,** each as a call costing 0;
  - **for each candidate:** both restatements, both draft cards, both verdicts
    with probabilities, the agreement call, A's download result, B's snippet
    match, any blocklist match, the band with its reason code, the card language
    with its word counts, and the languages of the card and the excerpt;
  - **repeats and settles:** each repeat with the candidate it matched and its
    probability, and each settle with the settling utterance's id;
  - **context and location:** the date, time and place context each stage was
    given; every raw location fix (coordinates, accuracy, time); every geocoder
    response; a denied location permission; geocoder failures;
  - **session events:** Pause and End, and every card sent, withdrawn, shown
    and filed, with the times the page reported;
  - **failures:** failures and outages, copied from the failure log, and gaps
    in speech-to-text.
- **Gaps:**
  - A dropped page–server connection loses its gap. No audio is buffered or
    replayed, and the session still counts as recorded completely.
  - While speech-to-text is being reopened but audio still reaches the server,
    the recording keeps writing that audio. The event log marks the gap, so a
    replay knows the live run didn't hear that stretch.
- **Expiry:** recordings are deleted 180 days after they were written, by a
  lifecycle rule. Correcting a recording doesn't delete its raw logs.

### The test corpus Markdown

Each recording session becomes one file, `corpus/<id>.md`. The
[variant C prototype](prototypes/recording-markdown/variant-c-blocks.md) shows
its shape.

1. **Header:** a fenced `yaml carl-session` block containing:
   - the session id;
   - the place, rounded to neighbourhood and town, never coordinates. If the
     session moved, each place is listed in order;
   - the listening time, the config file and its hash, and the cost;
   - the correction `status`: `not started`, `in progress` or `done`;
   - `same_speaker` pairs, where the owner merges labels across streams (for
     example `[[A2, B1]]`). There are no names.

   Every file records its format version.
2. **Transcript:** readable lines such as `**A2** · 00:04:31 · text`, with time
   counted from Start. Small talk and skipped backchannel are included, and
   "paused" and "gap" markers sit at stream boundaries.
3. **Candidates:** a fenced `yaml carl-candidate` block right after each
   candidate's utterance, filled in by the generator. It holds:
   - Carl's id (C1…), the kind, whether it was shown (`plain`, `hedged` or
     `no`), whether it was late, and the check time;
   - the card text and source;
   - both fact-finders' restatements;
   - the verdict summary: both outcomes, p(same fact), p(supported) for each
     card, how each excerpt was verified, and the band's reason code.

   A repeat's block holds `repeat_of: Cn` and its probability instead.
4. **Owner fields:** each block has `mark` and `note`. The values for `mark`
   are:
   - for a shown card: `deserved`, or one of `wrong`, `nitpick`, `opinion`,
     `contested`, `already settled` and `not checkable`;
   - for a silent candidate: `ok` or `should show`;
   - for a repeat: `ok` or `bad match`, with a note saying what it should have
     been.
5. **Missed candidates:** the owner adds a `yaml carl-missed` block (`kind`,
   `should_say`) under the utterance Carl should have caught.
6. **Transcript fixes only around candidates:** the owner fixes errors that
   change a candidate, a missed one, or the context they need. The rest stays
   as speech-to-text heard it, so the corpus is not a word-error-rate
   reference.

### Correcting it

- **`generate <id>`** writes `corpus/<id>.md` as a pure function of the
  `recordings/<id>/` event log.
  - It refuses to overwrite a file whose status isn't `not started`, so
    corrections are never lost.
  - It is run by hand after the session. The format can therefore change, and
    drafts can be regenerated until correction starts.
- **`fetch <id>`** downloads the file, and the owner edits it in any editor.
- **`put <file>`** runs `check` and then uploads over `corpus/<id>.md`.
  - `check` rejects unknown mark values; changed or missing candidate ids,
    utterance times or speaker labels; and `same_speaker` labels that don't
    exist.
  - With `status: done`, it also requires a mark on every candidate and repeat
    block.
- The corpus Markdown never goes into the repo.

### Access and deletion requests

- Anyone recorded may ask to hear or read their session, or to have it
  deleted. The owner honours a request without asking why.
- The owner uses the script's `list`, `export <id>` and `delete <id>`.
  Delete removes the whole session: `recordings/<id>/` and `corpus/<id>.md`.
- The providers' own copies are outside Carl's control.
  - The documentation names each stage's provider and links to its retention
    terms.
  - OpenAI keeps abuse logs for up to 30 days.
  - Perplexity's Agent API keeps responses on its servers even with
    `store: false`, for an undocumented period.

Sources: [Development mode and the recording-session disclosure][t21],
[Where the card archive, failure log and recording sessions are kept][t11],
[Turning a recording session into owner-correctable Markdown][t14],
[What "done" means for the first working version][t01],
[What runs in the browser and what runs on a server][t06],
[The can't-hear-or-check state and the failure log][t22],
[Location in the pipeline and the test corpus][t20],
[Prompts, card language and the source blocklist][t23],
[Splitting verdict confidence into plain, hedged and silent][t10],
[Search providers' terms and Luna web search][t17], [product spec][product].

## 10. Failures and outages

### One state, two wordings

- The listening indicator's "can't hear or check" state reads either "Can't
  hear" or "Can't check".
- The server sends a reason code. If both apply, "Can't hear" wins.
- The time spent in this state is an **outage**. The failure log records each
  outage's start and end.
- A single failed check shows nothing, and no error text ever appears on
  screen.

### Can't hear

The indicator switches to "Can't hear" when:

- **the page–server connection drops.** The page switches as soon as the
  WebSocket closes, or when no server message (heartbeat or other) has arrived
  for **10 s**. A server restart shows up this way. The server likewise
  treats 10 s without any message from the page as a dropped connection, and
  starts the reconnect grace period;
- **the microphone is lost.** The microphone track ends or is muted: permission
  is revoked, a phone call takes the microphone, or the page is hidden;
- **the speech-to-text connection drops,** while the server reopens it with
  backoff;
- **no audio arrives.** While listening, the server receives no audio chunk for
  **5 s**.

These are not failures:

- the planned handover at about 50 minutes. If the new socket fails to open,
  that counts as a dropped connection;
- Pause, which has its own state;
- long silence at the table.

"Can't hear" clears as soon as audio flows end to end again: the socket is
back, the microphone is live, the speech-to-text stream is open and audio is
arriving.

### Can't check

- One failed candidate stays silent. The indicator switches only when a stage
  is down:
  - the decision model, counting decision and settle calls together, after
    **3 failed calls in a row**;
  - fact-finding or fact-checking after **2 failed candidates in a row**.
- A failure is any typed error: timeout, unavailable, rate-limited or bad
  output.
- "Can't check" clears on the stage's first success. There are no health
  probes, so a fact-finding or fact-checking outage lasts until the next
  candidate succeeds.
- **One fact-finder down while the other works is not "Can't check".** Carl
  checks with the one that works, so only hedged cards are possible.
  - Each failure is logged as `fact-finding A` or `fact-finding B`.
  - Fact-finding counts as failed for a candidate only when both fact-finders
    fail on it.
- `overload` is logged but never changes the indicator.
- The 60 s candidate timeout is logged against the stage the candidate was
  stuck in, and counts as a failure of that stage.
- **Utterances during a decision outage are dropped,** not retried later,
  because a card minutes late is worthless. Each utterance still gets its
  decision call, since only a successful call can end the outage; an utterance
  whose call fails is dropped. The outage's log entry counts the dropped
  utterances. A repeat said after recovery is checked as usual.

### The failure log

- **Each entry** holds:
  - the time;
  - the stage: `speech-to-text`, `decision`, `settle`, `fact-finding A`,
    `fact-finding B`, `fact-checking`, `connection` or `mic`;
  - the kind: `timeout`, `unavailable`, `rate-limited`, `bad-output`,
    `dropped`, `overload`, `lost-in-restart`, `no-audio` or `mic-lost`;
  - the provider and model id;
  - the HTTP status or the provider's error code;
  - the session id;
  - Carl's candidate id (`C3`), when there is one.
- **Outages** get a start, an end and the number of utterances skipped.
- Entries hold no conversation content and no free-text provider message,
  since some providers' messages echo the prompt. A recording session's event
  log keeps the full error text.
- The failure log is stored under `failures/` in the bucket and deleted after
  30 days. Recording sessions also copy failures into their event log.
- Viewing it (the Log) and clearing it come in the next version.
- **Not failure-log entries:** a denied location permission, a geocoder
  failure, an excerpt that couldn't be downloaded or wasn't found, and a
  recording stop.

### What the page buffers

Some failures only the page can see. It keeps them in memory and sends them on
reconnect:

- the connection gap, with its start and end;
- the microphone being lost (track ended or muted, or permission revoked);
- the page being hidden;
- the wake lock being refused or released during a session;
- a card that failed to render.

Losing the wake lock doesn't change the indicator on its own. Only the
microphone actually stopping does.

### Session continuity

- **Dropped connection.**
  - The page sends End on `pagehide` when it can.
  - Otherwise the server keeps the session for a **2-minute grace period**,
    waiting for the page to reconnect, then ends it.
  - Checks already running carry on during the drop. The container must
    therefore keep its CPU while no page is connected; build step 1 measures
    whether it is throttled.
  - On reconnect, the server sends the current card and the card history again.
- **Server restart or scale-down.**
  - The server saves session state to `sessions/<id>/state.json` as it
    changes. The state holds recent utterances for the decision context, open
    candidates, cards shown, the running cost and the current place name.
  - After a restart, the page reconnects as above and the session carries on.
  - Checks lost in the restart go into the failure log as `lost-in-restart`.
  - At every start, the server looks in `sessions/` and gives each session's
    page the 2-minute grace period to reconnect. A session whose page doesn't
    come back is ended as usual. A 1-day lifecycle rule on `sessions/` removes
    any state still left behind, since it holds recent conversation.
- **The handover at about 50 minutes** (see [Hosting](#hosting)) is planned and
  loses nothing. Until build step 7 builds it, the reconnect grace period
  covers Scaleway's 60-minute cut. The cut then loses a second or two of audio,
  marked as a gap.
- **Speech-to-text drops** are handled as in
  [The speech-to-text stream](#the-speech-to-text-stream): the stream reopens
  with backoff, speaker labels start afresh, and the context gets a "(gap)"
  marker.
- Every hosting platform can drop long connections, so Carl must reconnect
  cleanly wherever it runs.

Sources: [The can't-hear-or-check state and the failure log][t22],
[What runs in the browser and what runs on a server][t06],
[How audio is streamed and how speaker labels reach the decision model][t08],
[Where the card archive, failure log and recording sessions are kept][t11],
[Hosting and secrets][t13],
[Location in the pipeline and the test corpus][t20],
[Splitting verdict confidence into plain, hedged and silent][t10],
[Development mode and the recording-session disclosure][t21],
[Hosting a small backend with streaming connections and secrets][t05],
[Build order][t25].

## 11. Cost metering

- **A price table in the config file** gives each model's rates: input, cached
  and output tokens, per search, and per audio hour.
  - Each adapter works out a call's cost from the provider's usage fields.
  - When a provider also reports its own cost (Perplexity, for example), both
    figures are recorded. The provider's figure counts toward the totals, and
    the difference is logged.
  - The price table is part of the config copy each recording stores.
- **Calls with unknown usage** (a timeout, a dropped connection, bad output
  without usage) get an estimate. It is based on the input tokens Carl sent
  plus the stage's typical output size, and is marked as estimated. It is never
  counted as zero or skipped.
- **What counts** is per-use charges only:
  - speech-to-text stream time, including the reconnect grace period, since
    the stream stays open then. Pause isn't counted, since the stream is
    closed;
  - the decision model's calls (decision and settle), the fact-finding calls,
    the fact-checking verdicts and agreement calls;
  - search fees.

  Fixed hosting fees are left out. Source-page downloads are recorded as calls
  costing 0, so their number and response times still show.
- **Months** are calendar months in Europe/Helsinki time. Each call is dated by
  its own timestamp, so a session that crosses into a new month splits its
  cost between the two.
- **Totals** are kept in `costs/` in the bucket, indefinitely, since they hold
  no conversation content:
  - a cost summary for each session: start, duration, and cost per stage split
    into actual and estimated;
  - a month-to-date total, updated on every call.

  Per-call costs also go into a recording's event log.
- **Currency:** costs are stored in USD, as billed. They are shown in euros at a
  fixed rate from the config file, marked "≈". The rate starts as the European
  Central Bank's reference rate on the day the config file is first written,
  and is updated by hand when it drifts by more than about 5%.
- **What the owner sees:**
  - the Start screen shows the month-to-date total and the last session's line
    (date, length, cost, €/h);
  - the "Session ended" summary shows the session's cost;
  - nothing about cost appears during a session.
- **Checking against the bills** is done by hand now and then. The owner-only
  script prints month totals per provider for this. There is no automatic
  reconciliation.
- **Backstop:** a hard monthly spend limit is set in every provider dashboard
  that offers one, while the monthly budget and its warning wait for the next
  version.

Sources: [Metering running cost against the monthly budget][t12],
[Hosting and secrets][t13], [The screen][t24],
[Development mode and the recording-session disclosure][t21].

## 12. Location

### From coordinates to a place name

- The page sends raw coordinates and their accuracy to Carl's server, and the
  server turns them into a place name. The page makes no third-party calls.
- The server reverse-geocodes with **Nominatim**, the public OpenStreetMap
  service:
  - it sends its own User-Agent, caches results, and makes at most 1 request a
    second;
  - it is free at a few calls per session, has Finnish neighbourhoods, and
    works abroad;
  - its ODbL licence allows storing its results.
- Names are kept as Nominatim returns them, so neighbourhoods are in Finnish.
- A place name has four parts: neighbourhood, city, region and country.
- The coordinates reach Nominatim, which may log them. The disclosure line
  already covers location going to cloud services.

### What each stage gets

| Stage | Location context |
| --- | --- |
| Decision call | Place name (neighbourhood, city, country), with local date, time and timezone |
| Fact-finders' prompt | The same as the decision call |
| Fact-finder A's search tool (OpenAI `web_search`) | `user_location` `{type: "approximate", city, region, country, timezone}` |
| Fact-finder B's search tool (Perplexity `web_search`) | `user_location` with city, region and country |
| Settle call | Date and time only |
| Fact-checking model (verdicts, agreement call) | Date and time only |

- **Coordinates never go to any model.** The place context is at
  neighbourhood level, never at street level.
- OpenAI's `web_search` defaults to the United States if it gets no location.

### Updates during a session

- While the session runs, the page runs `watchPosition`. It stops while the
  session is paused.
- After its first fix, the page sends a new one only when:
  - the phone has moved more than **500 m** from the last fix it sent; or
  - the accuracy has moved up a level. The levels are the cuts under
    [Off, denied, poor fix, geocoder down](#off-denied-poor-fix-geocoder-down):
    no location, town only, and the full place name.
- The server geocodes again only when a new fix falls outside the last result's
  neighbourhood, and at most once a minute. At a dinner table, that means one
  geocoding call per session.

### Off, denied, poor fix, geocoder down

- **The Location switch** is on the Start screen. It is on the first time Carl
  is opened, and the phone remembers it after that. When it is off, the page
  never asks for location, and stages get only the date, time
  and timezone. The timezone comes from the phone.
- **Permission denied** works the same as off, and Carl doesn't ask again. It
  is noted once in the recording session's event log. It isn't a failure-log
  entry, since Carl can still hear and check.
- **A poor fix:** with accuracy worse than 1 km, stages get the town only. With
  accuracy worse than 20 km, they get no location.
- **Geocoder failure:** Carl keeps the last place name, or has none if there
  wasn't one yet. The failure goes into the event log, not the failure log.
- The date and time always come from the server clock, in the phone's
  timezone.

### What each record keeps

| Record | Location kept |
| --- | --- |
| Recording session's event log (deleted after 180 days) | Every raw fix sent (coordinates, accuracy, time), every geocoder response, and the place context each model call was given |
| Test corpus Markdown | The header's `place:` field with neighbourhood and town, and each place in order if the session moved. Never coordinates |
| Session state | The current place name only, never coordinates. Deleted at End |
| Card archive, failure log, cost summaries | None |
| A normal (not recording) session | Coordinates only in server memory, gone at End |

Sources: [Location in the pipeline and the test corpus][t20],
[Turning phone coordinates into a place name][t19],
[Development mode and the recording-session disclosure][t21].

## 13. Config file contents

The config file is committed and baked into the image, and changing it means a
redeploy. Each recording session stores a copy. Anything the test corpus or an
early measurement might tune goes in it:

| Setting | Starting value |
| --- | --- |
| Each stage's provider, model and parameters, including Soniox's `language_hints: [fi, en]` | See [Provisional models](#provisional-models) |
| Soniox `max_endpoint_delay_ms` | 1,500 ms |
| False speaker switch | 2 words or fewer |
| Longest utterance | About 30 s, then split at the next sentence end |
| Backchannel and filler list | joo, niin, aha, mm, jaa, okei, yeah, right, uh-huh, wow… |
| Decision context window | Up to 10 utterances, from no more than the last 2 min |
| Repeat threshold (the `same as` choices together) | 0.5 |
| Candidate threshold (`claim` + `open question`) | 0.5 |
| Settle threshold | 0.5 |
| Most live candidates at once | 8 |
| Candidate timeout | 60 s after its utterance |
| Wait for the second fact-finder | About 12 s after the first arrives |
| Source-page download timeout | About 3 s |
| Plain band: p(same fact) | ≥ 0.7 |
| Plain band: p(supported), shown card | ≥ 0.85 |
| Plain band: p(supported), other card | ≥ 0.5 |
| Hedged band: p(supported) | ≥ 0.6 |
| Source blocklist (domain suffixes) | Forums and Q&A sites (such as Reddit, Quora), social media, video platforms, user-edited wikis other than Wikipedia |
| Card-language window | 10 min |
| Card-language word minimum | About 50 words |
| Least time on screen while another card waits | 8 s |
| Late-card cut-off | 20 s after the utterance, measured when the card would reach the screen |
| Heartbeat, each way | Every 3 s when nothing else was sent |
| Silence before a side treats the connection as dropped | 10 s |
| Reconnect grace period | 2 min |
| WebSocket handover | About 50 min |
| "Can't hear": no audio (server) | 5 s |
| "Can't check": decision model | 3 failed calls in a row |
| "Can't check": fact-finding, fact-checking | 2 failed candidates in a row |
| Movement before a new location fix is sent | 500 m |
| Location accuracy | Worse than 1 km: town only. Worse than 20 km: none |
| Geocoding again | Only outside the last neighbourhood, at most once a minute |
| Price table | Per model: input, cached and output tokens; per search; per audio hour |
| USD → € rate | The European Central Bank's reference rate on the day the file is first written |

These stay out of the config file. They follow a provider's limit, a usage
policy, a data format or a security choice, not anything the corpus would tune:

| Value | Setting | Where |
| --- | --- | --- |
| Soniox reopen backoff | 1, 2, 4… up to 30 s | Code |
| Soniox stream rotation | Before its 300-minute limit, at a segment end | Code |
| Audio chunk, page to server | About 100 ms | Code |
| Recording audio objects, event-log flush | About 1 min each, about every 10 s | Code |
| Nominatim rate | At most 1 request a second | Code |
| Wrong access pass | Answered after 1 s | Code |
| Access-pass cookie | 1 year | Code |
| Loading page | Shown after 2.5 s without an answer | The Worker |
| Bucket lifecycle rules | `recordings/` 180 days, `failures/` 30 days, `sessions/` 1 day | The bucket |

Sources: [Provisional models for each stage][t07],
[How audio is streamed and how speaker labels reach the decision model][t08],
[Decision model context and candidate de-duplication][t09],
[Splitting verdict confidence into plain, hedged and silent][t10],
[Where the card archive, failure log and recording sessions are kept][t11],
[Metering running cost against the monthly budget][t12],
[Hosting and secrets][t13], [Tracking a candidate until its card][t18],
[Location in the pipeline and the test corpus][t20],
[The can't-hear-or-check state and the failure log][t22],
[Prompts, card language and the source blocklist][t23],
[What runs in the browser and what runs on a server][t06],
[product spec][product], [Decided at arrival](#16-decided-at-arrival).

## 14. Build order

### Ground rules

1. **Record dinners before cards are live.**
   - Recording starts at step 2, once the disclosure screen, the recording mark
     and the one-way stop-and-delete work.
   - These dinners supply audio for later replays; they don't test Carl's
     cards.
   - The config and commit that each recording stores show which stages were
     off.
2. **A step is done** when both of these hold:
   - pytest passes on the pure logic with fake adapters. That logic covers
     utterance splitting, the backchannel skip, the repeat and candidate
     thresholds, the bands, the late-card cut-off and the cost maths. GitHub
     Actions runs it on every push to `main`, with no live provider calls in
     CI;
   - the step is deployed and used for one session on the phone, at a real
     dinner or with a Finnish radio talk show playing beside it.
3. **Dev file source:** a local-only way to send an audio file over the
   WebSocket instead of the microphone. It is a development aid, not the replay
   and scoring harness.
4. **The order stops at done.** What comes after is listed, unordered, in
   [Next version](#15-next-version).
5. **Implementation tickets:** when coding starts, each step becomes one ticket
   in a new `.scratch/<build-effort>/` folder. A step too big for one agent
   session is split there. The tickets are in
   [`.scratch/build-first-working-carl/`](../build-first-working-carl/issues/).

### Early checks

| Check | When | What it gates, and the fallback |
| --- | --- | --- |
| Luna with OpenAI web search (Responses API, effort `none`, `tool_choice: required`, JSON) | Step 0 | Fact-finder A. Fallback: Luna on Perplexity |
| Gemini 3.8 Flash with `web_search` and a JSON schema on Perplexity's Agent API | Step 0 | Fact-finder B. Fallback: another non-OpenAI model on Perplexity's Agent API, or as a stopgap fact-finder A alone (hedged cards only) |
| TypeSafe Jev giving typed answers with probabilities, in Finnish | Step 0 | Fact-checking. Fallback: Gemini 3.5 Flash-Lite |
| A 2-hour WebSocket through Cloudflare's proxy to the container: the real cut, CPU throttling with no page connected, and cold start | Step 1 | The handover design. Fallback: a Scaleway Instance ([ADR 0002][adr2]) |
| Android Chrome for 2 hours: AudioWorklet at 16 kHz, wake lock, microphone kept, heat and battery | Step 2 | The page |
| Soniox at a real table: Finnish, code-switching, speaker attribution at 1–2 m | The first recorded dinner | Nothing. It shows early how good Soniox is |
| The owner reads OpenAI's and Perplexity's legal terms (a job for the owner) | Before the first dinner with fact-finders (step 4) | Keeping search results in recordings |

### The steps

0. **Provider smoke test:** a local, throwaway script with Finnish and English
   inputs.
   *Leaves:* each text stage's provisional model confirmed, or its fallback
   chosen. Nothing is built until this is settled.
1. **Skeleton in the cloud:**
   - the Python server and page shell, from drum-transcribe's pieces: the
     access-pass gate, the loading Worker, the Dockerfile and the deploy
     commands;
   - the bucket, with its 180-, 30- and 1-day rules;
   - the config file and the `prompts/` folder;
   - pytest in GitHub Actions;
   - a WebSocket with a heartbeat;
   - then the 2-hour connection test.

   *Leaves:* `faktat.vempai.men` opens behind an access pass, and the real cut,
   throttling and cold start are known.
2. **Recorder:**
   - AudioWorklet microphone → server → Soniox, and utterance splitting;
   - audio chunks and the JSONL event log in `recordings/<id>/`, with the copy
     of config, prompts and commit;
   - the Start screen with the Record switch and costs, the disclosure screen,
     the Listening and Recording pills, stop-and-delete, Pause, End and the
     wake lock;
   - the 2-minute reconnect grace period;
   - speech-to-text cost metering and the month's total;
   - the "Session ended" summary (its card count shows from step 4 on);
   - the owner script's `list`, `export` and `delete`;
   - the dev file source.

   *Leaves:* dinners recorded, with no checks yet.
3. **Decision model:** decision calls with their context, the backchannel skip,
   repeats, card language, and location (`watchPosition` and Nominatim).
   Candidates are recorded, not shown.
   *Leaves:* dinners that record what Carl would have checked.
4. **First cards:**
   - fact-finder B, or A if B failed the smoke test;
   - excerpt matching, the blocklist and fact-checking verdicts, with hedged
     cards only;
   - the session screen: top bar, current card, card history, pacing, late-card
     cut-off.

   *Leaves:* cards live at the table.
5. **Second fact-finder:** both fact-finders in parallel, the wait of about
   12 s, A's page download, the agreement call and the plain band.
   *Leaves:* the full split into plain, hedged and nothing.
6. **Tracking candidates:** the whole settle call with the drop rule (`agrees`
   is recorded; the mark comes later), the cap of 8, the 60 s timeout, and cards sent again after a
   reconnect.
7. **Robustness:**
   - "Can't hear" and "Can't check";
   - the failure log, with server entries and the page's buffer;
   - resuming from `state.json`;
   - the ~50-minute handover with no gap;
   - reopening Soniox with backoff, and stream rotation.

   Until this step, the reconnect grace period covers the 60-minute cut, losing
   a second or two of audio, marked as a gap.
8. **Corpus and costs:** `generate`, `fetch`, `put` and `check`, run then over every
   dinner recorded so far; the per-session cost summary; the Start screen's
   last-session line.
9. **Acceptance:** one 2-hour recorded dinner runs end to end. This is **done**.

Sources: [Build order][t25].

## 15. Next version

Deferred from the first version, in no particular order:

- **The "Settled at the table" / "Ratkesi pöydässä" mark.** The settle call
  that feeds it is already in the first version.
- **The live transcript line,** with its switch.
- **The ⋯ menu** in the top bar, holding the transcript-line switch and the
  Log.
- **The Log menu:** viewing and clearing the failure log. The first version
  already writes the log.
- **Ending a session after 30 minutes without an utterance,** paused or not.
- **The card archive:**
  - at End, the page pulls the session's cards and listening time from the
    server into IndexedDB, requests `navigator.storage.persist()` and offers
    export;
  - the server deletes its copy once the page confirms;
  - between sessions the owner marks cards Wrong or Pointless and adds a note
    of missed moments;
  - it opens only when no session is running;
  - nothing in the first version blocks it. Until then, a normal session's
    cards are thrown away at End.
- **Setting the monthly budget and its warning mark** on the listening
  indicator and the Start screen. Going over the budget never stops Carl. Cost
  metering already keeps the month-to-date total that the warning compares
  against.

The tickets mention a few more possible additions, with no version given:
storing recordings as FLAC, an in-app page for access and deletion requests,
and roles for access passes if a pass is ever given to someone else.

The full vendor and model comparison against the test corpus is a separate
effort (see [Out of scope](#out-of-scope)).

Sources: [Build order][t25],
[What "done" means for the first working version][t01],
[Where the card archive, failure log and recording sessions are kept][t11],
[Metering running cost against the monthly budget][t12],
[Development mode and the recording-session disclosure][t21],
[The screen][t24], [product spec][product].

## 16. Decided at arrival

Assembling this spec turned up conflicts between tickets and gaps that no
ticket settled. They were settled on 2026-09-26, while the spec was being
assembled. None has a ticket of its own, so this list is their record. The
sections above already follow them.

**The owner's rulings**

- The fact-checking model never sees the fact-finders' restatement.
  [Decision model context and candidate de-duplication][t09] stands over an
  aside in [Location in the pipeline and the test corpus][t20].
- The words Carl adds to a card (label, hedged tag, settled mark) follow the
  card language, as in [Prompts, card language and the source blocklist][t23].
  Everything else Carl shows is in English.
- Speech-to-text goes through the server rather than straight from the browser,
  because relaying works with any provider.

**Judgement calls the owner asked for.** Each is cheap to change.

| Gap | Decision | Why |
| --- | --- | --- |
| The hedged tag in Finnish | "Varauksin" | Short enough to read across the table, and it means "hedged" |
| Tapping a card's source | Opens the source in a new tab, and the card stays. A tap anywhere else moves on | OpenAI requires a shown citation to be clickable, and a separate target keeps the card's tap-to-move-on |
| The settle call in the first version | The whole call, with `agrees` and `disputes` for the card on screen. `agrees` is recorded but not shown | The next version's mark becomes a screen-only change, and the test corpus gets the data now |
| Decision calls during a decision outage | Every utterance still gets one. An utterance whose call fails is dropped | There are no health checks, so only a successful call can end the outage |
| The heartbeat | Every 3 s each way when nothing else was sent. 10 s of silence means a dropped connection, on both sides | The page reports "Can't hear" only after three missed beats, and the server notices a dead link it wasn't told about |
| Page-side thresholds | The server sends them to the page at session start | The config file stays the one source of every threshold |
| Location defaults | The switch is on the first time, then remembered. A fix is sent when accuracy moves up a level (none, town, full place). The 1 km and 20 km cuts are in the config file | The product spec's disclosure line assumes location is on unless switched off, and the levels are the ones the stages already use |
| Word language in the speech-to-text interface | Every word carries a language code. A one-language-per-stream provider tags every word with the stream's language | Card language needs it, whichever provider is plugged in |
| The owner script's `fetch` | `export <id>` gets everything for an access request, with the audio as one WAV. `fetch <id>` gets only the corpus Markdown | Correcting shouldn't download hundreds of megabytes of audio, and someone asking to hear a session needs a playable file |
| Session state left behind | At every start the server waits the grace period for each session's page, then ends it. A 1-day lifecycle rule on `sessions/` is the backstop | The state holds recent conversation, so it mustn't linger |
| The ⋯ menu | Not in the first version | Both its items belong to the next version |
| The "Session ended" summary | Built with the recorder (step 2), card count from step 4 | Everything else it shows exists from step 2 |
| The USD → € rate | The European Central Bank's reference rate on the day the config file is first written, updated by hand when it drifts more than about 5% | Costs are shown only as approximate ("≈") |
| Config file or code | Anything the corpus or a measurement might tune goes in the config file. Provider limits, usage policies, data formats and security choices stay in code, the Worker or the bucket | That keeps the config file to what the comparison will tune |

Every other conflict between tickets went to the later ticket, as the
introduction says. The recording disclosure keeps the exact wording from
[Development mode and the recording-session disclosure][t21]. Providers' own
logs are left to the documentation (see
[Access and deletion requests](#access-and-deletion-requests)).

[product]: ../purpose-and-goal/spec.md
[context]: ../../CONTEXT.md
[adr1]: ../../docs/adr/0001-typed-judges-around-a-writing-search.md
[adr2]: ../../docs/adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md
[t01]: issues/01-done-for-first-version.md
[t02]: issues/02-streaming-speech-to-text.md
[t03]: issues/03-models-for-text-stages.md
[t04]: issues/04-phone-browser-capabilities.md
[t05]: issues/05-hosting-small-backend.md
[t06]: issues/06-browser-and-server-split.md
[t07]: issues/07-provisional-models.md
[t08]: issues/08-audio-and-speaker-labels.md
[t09]: issues/09-decision-context-and-dedup.md
[t10]: issues/10-confidence-bands.md
[t11]: issues/11-storage-expiry-deletion.md
[t12]: issues/12-cost-metering.md
[t13]: issues/13-hosting-and-secrets.md
[t14]: issues/14-recording-to-markdown.md
[t15]: issues/15-parakeet-v3.md
[t16]: issues/16-scaleway-hosting.md
[t17]: issues/17-search-terms-and-luna.md
[t18]: issues/18-tracking-candidate-until-card.md
[t19]: issues/19-reverse-geocoding.md
[t20]: issues/20-location-in-pipeline.md
[t21]: issues/21-development-mode-and-disclosure.md
[t22]: issues/22-cant-hear-or-check.md
[t23]: issues/23-prompts-and-card-language.md
[t24]: issues/24-the-screen.md
[t25]: issues/25-build-order.md
