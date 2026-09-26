# Map: First working Carl

Label: wayfinder:map

## Destination

A decided plan for the first working version of Carl at
`.scratch/first-working-carl/spec.md`, clear enough that implementation can
start without open questions. That version is a web page, opened on the
owner's phone, that runs the whole pipeline end to end (mic → speech-to-text →
decision model → fact-finding model → fact-checking model → fact card on
screen) with provisional models behind the swappable interfaces `AGENTS.md`
requires, and includes development mode, so real dinners can be recorded as
**recording sessions** to start the **test corpus**.

## Notes

- **The output is a plan, not code.** Tickets resolve decisions; nothing here
  builds Carl. When the frontier is empty, assemble `spec.md` from the resolved
  tickets: that is arrival, not a ticket.
- **The product spec is settled.** [`.scratch/purpose-and-goal/spec.md`](../purpose-and-goal/spec.md)
  fixes behaviour and success criteria. Don't reopen it; if building proves a
  behaviour impossible, raise it with the owner. Its rationale lives in the
  [Purpose and goal map](../purpose-and-goal/map.md) and its tickets.
- **Provisional models only.** Pick models only as far as needed to build and
  record. The rigorous comparison is a later map (see Out of scope).
- **Hedge, don't refuse; precision over recall.** Finnish and English, fully.
- **Vocabulary:** use `CONTEXT.md` exactly (session, owner, table, utterance,
  candidate, claim, open question, verdict, fact card, hedged fact card, card
  history, card archive, late card, check time, failure log, monthly budget,
  recording session, test corpus). Grilling tickets also call
  `domain-modeling`; research tickets use the `research` skill.
- **Research** lives in `docs/research/`: start from
  [realtime-fact-checking.md](../../docs/research/realtime-fact-checking.md),
  [prior-art-live-fact-checking.md](../../docs/research/prior-art-live-fact-checking.md)
  (precision from concurrence and claim matching, not self-reported
  confidence) and [previous-carl-lessons.md](../../docs/research/previous-carl-lessons.md)
  (its stale, implementation-level lessons are relevant here: structured
  verdicts before anything renders, dedupe in Carl's own state, silent
  failures, one prompt source of truth, wake lock, no single-flight queue).
- **Git:** work directly on `main`; commit and push to `main`, no feature
  branches or pull requests (the owner's standing preference). Research
  findings go straight to `docs/research/` on `main`.

## Decisions so far

<!-- one line per resolved ticket: [title](issues/NN-slug.md): gist -->

- [What a phone browser allows a web page to do](issues/04-phone-browser-capabilities.md): iOS mutes the mic whenever the page is hidden, so a session needs a wake lock (Home Screen apps from iOS 18.4); iOS deletes a Safari tab's storage after 7 days unused, so on-phone data needs a Home Screen web app with `persist()` plus export; Android evicts only under disk pressure; 2 h of 16 kHz Opus is ~22 MB
- [Models for the decision, fact-checking and message-writing stages](issues/03-models-for-text-stages.md): the decision model costs cents per hour except Haiku 4.5 (~$0.63/h); search fees drive the fact-checking cost (a few cents to ~$0.90/h); no calibrated confidence anywhere, so two verifiers from different vendors agreeing is the practical signal; Perplexity Sonar ends 2026-09-27; Google grounding forbids storing results (clashes with recording sessions); all keys belong on a server; no published Finnish scores, and speed must be measured
- [Streaming speech-to-text for Finnish and English table audio](issues/02-streaming-speech-to-text.md): only AssemblyAI Universal-3.6 Pro Streaming (~$0.57/h) and Soniox stt-rt-v5 (~$0.12/h) document Finnish, Finnish/English code-switching and streaming diarization; Speechmatics and Deepgram do Finnish but one language per stream; Google, OpenAI, ElevenLabs, xAI and Azure drop out; the browser can connect directly with a short-lived token, and Carl splits finals at speaker changes to get utterances
- [Hosting a small backend with streaming connections and secrets](issues/05-hosting-small-backend.md): Cloudflare Workers + Durable Objects + R2 meets every need for $0–5/month (no hard connection limit, EU storage, secrets, automatic deletion after N days, Access for an owner-only login, hosts the page too); Fly.io and a Helsinki VPS also fit; Vercel and Cloud Run can't hold a 2 h connection; every host can drop sockets, so Carl must reconnect cleanly
- [What "done" means for the first working version](issues/01-done-for-first-version.md): Android Chrome on the owner's phone; development mode first, with fact cards shown live in recording sessions; card archive, settled mark, live transcript line, budget setting and warning, Log menu and 30-min silence end wait; no quality targets, done = a 2 h session runs end to end and is recorded completely (every STT event and model call with its config, latency and cost); cost metered from the start
- [Scaleway as Carl's host](issues/16-scaleway-hosting.md): Cloudflare still fits better; Scaleway serverless caps requests at 60 min and can't do owner-only WebSocket access; an Instance (~€0.43–6.55/month + IPv4) is a Hetzner-like option; Object Storage lifecycle meets 6-month deletion; an L4 GPU for Parakeet costs ~€1.75/session, Vast.ai is cheaper but a poor home for private audio
- [Running Parakeet v3 for Carl's speech-to-text](issues/15-parakeet-v3.md): Parakeet v3 alone doesn't fit (offline-only, no diarization, weak code-switching); NVIDIA's Nemotron streaming ASR + diarization is the self-hosted pair to try (weaker Finnish); not viable in the phone's browser; free on the owner's GPU machine; Vast.ai is no cheaper than Soniox
- [What runs in the browser and what runs on a server](issues/06-browser-and-server-split.md): thin page (mic, screen, wake lock, location, taps), whole pipeline and all keys on a server; a network drop loses its gap; 2-min reconnect grace before a session ends, server holds the cards and re-sends them; a server restart resumes from saved state; Pause stops the mic and closes the speech-to-text connection
- [Provisional models for each stage](issues/07-provisional-models.md): no message-writing model; decision (GPT-6 Luna) and fact-checking (TypeSafe Jev, swap Gemini 3.5 Flash-Lite) give typed answers only; two fact-finding models search and write draft cards in parallel (GPT-6 Luna + OpenAI search, Gemini 3.8 Flash via Perplexity's Agent API); Soniox for speech-to-text; no Anthropic models; config file per deploy, stored with each recording session; ~$0.35–0.55/h
- [Search providers' terms and Luna web search](issues/17-search-terms-and-luna.md): OpenAI's and Perplexity's docs don't forbid storing or analysing results (unlike Google), but both vendors' full terms are unverified; OpenAI requires visible, clickable citations; Luna's model page lists OpenAI web search (Responses API, effort `none` = fast search); Gemini 3.8 Flash + `web_search` + JSON schema on Perplexity needs a test call; only Perplexity returns source snippets, OpenAI citations carry no excerpt
- [How audio is streamed and how speaker labels reach the decision model](issues/08-audio-and-speaker-labels.md): 16 kHz PCM chunks over one WebSocket (echo cancellation and noise suppression off); Soniox endpointing at 1,500 ms, stream kept open through the reconnect grace period, finalised then closed at Pause; utterances split at speaker changes with 1–2-word false switches merged and a ~30 s cap; speaker labels are scoped to their stream, with a marker at each Pause or gap
- [Decision model context and candidate de-duplication](issues/09-decision-context-and-dedup.md): one call per utterance (only pure backchannel skipped) with up to 10 utterances / 2 min of earlier context; choices `none / claim / open question / same as Cn` over the session's earlier candidates listed by Carl's own ids, each shown by the fact-finder's new standalone restatement; same = same assertion or question, not same topic; a repeat gets nothing unless the earlier one failed; thresholds in config
- [Splitting verdict confidence into plain, hedged and silent](issues/10-confidence-bands.md): wait for both fact-finders (~12 s after the first); plain needs agreement (a typed same-fact call) plus a verified excerpt (Perplexity snippet match or a downloaded page) and p(supported) ≥ 0.85; one verified card or a weaker pair is hedged (≥ 0.6) with a fixed "Todennäköisesti:"/"Probably:" prefix; contradictions, unverified excerpts and blocklisted sources show nothing; no category caps; each band recorded with a reason code
- [Where the card archive, failure log and recording sessions are kept](issues/11-storage-expiry-deletion.md): recordings in EU object storage under `recordings/<id>/` (raw PCM in ~1-min chunks + JSONL event log, written as the session runs), deleted by a 180-day lifecycle rule with no backups; corrected Markdown at `corpus/<id>.md`, no expiry; failure log in a small server store with 30-day expiry, page buffers its own failures; card archive later in the phone's IndexedDB, pulled from the server at End; an owner-only script lists, fetches and deletes whole sessions; host-default encryption only
- [Metering running cost against the monthly budget](issues/12-cost-metering.md): a price table in the config file turns each call's usage fields into USD (the provider's own figure wins when it reports one); unknown usage is estimated and flagged; per-use charges only, by Helsinki calendar month; per-session cost summaries and a month-to-date total kept indefinitely in the server store; Start screen shows the month total and the last session in ≈€; checked against provider bills by hand
- [Hosting and secrets](issues/13-hosting-and-secrets.md): following drum-transcribe, one Scaleway Serverless Container in Python (scaled to zero, max scale 1) at `faktat.vempai.men`, proxied by Cloudflare with the drum-transcribe "Starting up…" Worker; a WebSocket handover at ~50 min beats Scaleway's 60-min cap (measured early); several access passes (scrypt entries + 1-year HMAC cookie); one Scaleway bucket with a scoped key holds recordings, corpus, session state, failures (30-day rule) and costs; keys as container secret variables and in the password manager, provider spend limits set; one deploy by hand, staging runs locally under `dev/`; config baked into the image
- [Turning a recording session into owner-correctable Markdown](issues/14-recording-to-markdown.md): readable transcript with a fenced YAML block per candidate (verdict summary, reason code, card, check time) right under its utterance; the owner fills `mark`/`note` on shown cards (deserved or the spec's reasons), silent candidates (ok / should show) and repeats (ok / bad match), adds `carl-missed` blocks, merges speaker labels in the header and fixes the transcript only around candidates; script `generate` / `fetch` / `put` (with `check`), never overwriting a started correction
- [Tracking a candidate until its card](issues/18-tracking-candidate-until-card.md): a separate typed settle call runs per utterance while candidates are live; a settle drops a candidate before its card, and the settling utterance is checked on its own (so false corrections get cards); an on-screen card is marked "Settled at the table" only if the table agrees with it; no queue, one task per candidate with a cap of 8 and a 60 s timeout; the 20 s late-card cut-off is measured at display time; the page paces cards (at least 8 s each when another waits, in utterance order) and reports shown times
- [Turning phone coordinates into a place name](issues/19-reverse-geocoding.md): OSM data (Nominatim, Photon, Digitransit) has Finnish neighbourhoods (tested), mostly Finnish-only names; a few calls per session is free almost everywhere; OSM, Digitransit, OpenCage and Mapbox Permanent allow storing results indefinitely, Google, HERE, Mapbox Temporary and LocationIQ free restrict it; only self-hosting or a local polygon lookup keeps coordinates off third parties, OpenCage (`no_record`, EU) and Geoapify (≤24 h) retain least; OpenAI search takes city/region/country/timezone only (defaults to US), Perplexity takes coordinates plus country
- [Location in the pipeline and the test corpus](issues/20-location-in-pipeline.md): the page sends coordinates and accuracy, the server reverse-geocodes with Nominatim (cached, ≤1 req/s) to a neighbourhood-level place name; no model ever gets coordinates: decision and fact-finders get the place name plus local date, time and timezone, the search tools get city/region/country/timezone, settle and fact-checking get date and time only; `watchPosition` sends a fix after a 500 m move, re-geocoded only on leaving the neighbourhood; off or denied means date and time only (event-logged, not a failure); a fix worse than 1 km gives the town, worse than 20 km gives nothing; raw fixes only in the recording's event log, the corpus header lists places in order, no location in the archive, failure log or cost records
- [Development mode and the recording-session disclosure](issues/21-development-mode-and-disclosure.md): a "Record this session" switch on the Start screen, off by default each time, any pass; a disclosure screen (FI+EN line to read aloud) confirmed every time; the listening indicator's red recording dot shows only while audio is actually written (Pause hides it); tapping it gives a one-way "Stop recording?" that deletes everything recorded so far and continues as a normal session, leaving one line in the cost summary; a stop made offline is resent until the server gets it
- [The can't-hear-or-check state and the failure log](issues/22-cant-hear-or-check.md): one indicator state worded "can't hear" (connection drop or 10 s without server messages, mic lost, speech-to-text reopening, 5 s without audio) or "can't check" (decision down after 3 failed calls in a row, fact-finding or fact-checking after 2 failed candidates in a row; one fact-finder down doesn't count; `overload` never counts); back on the first success, no probes; utterances during an outage dropped and counted; log entries hold time, stage, kind, model, error code, session and candidate id, no free text; outages get a start and an end; the page buffers gap, mic, hidden, wake-lock and render failures; audio keeps recording while speech-to-text reopens
- [Prompts, card language and the source blocklist](issues/23-prompts-and-card-language.md): one English prompt file per stage under `prompts/`, the pipeline's own, baked into the image; version = content hash, each recording stores the config, all prompt files and the git commit, calls log name + hash + filled values; card language = majority by word count over the last 10 min (Soniox tags; the candidate's own below ~50 words or on a tie), no setting; fact-finders write the card in it and search in any language, excerpt stays verbatim; Carl adds label and hedge prefix; fact-checking judges across languages, no translation; blocklist = domain suffixes in config checked after the fact, prompt asks for primary or reference sources; hand-run FI+EN example cases per prompt, not CI
- [The screen](issues/24-the-screen.md): Carl follows the phone into portrait or landscape (landscape is the main case); a one-row top bar (indicator, recording mark, Pause, End with an "End the session?" confirm, ⋯); the current card takes most of the screen, the card history scrolls in small type in a right-hand column (landscape) or bottom strip (portrait); striped "Can't hear"/"Can't check" pill; layout A's round Start button with switches and costs beside or below it; Carl's own words in English, cards in the card language
- [Build order](issues/25-build-order.md): step 0 provider smoke test (Luna search, Gemini on Perplexity, Jev in Finnish); 1 cloud skeleton + 2 h connection test; 2 recorder (recorder-only dinners start); 3 decision model, candidates recorded; 4 first cards (fact-finder B, hedged only, session screen); 5 second fact-finder and plain band; 6 settle, cap, timeout; 7 robustness and gapless handover; 8 corpus script and cost summaries; 9 a 2 h dinner = done; each step pytest-green and used once on the phone; plain JS page, no build step; order stops at done

## Not yet specified

Nothing, and no ticket is open: the frontier is empty. Arrival is assembling
`spec.md` from the resolved tickets (see Notes).

## Out of scope

- **The rigorous vendor and model comparison** against the test corpus
  (word error rate, speaker attribution, precision/recall per stage, cost): a
  later, separate map that consumes the recordings this version makes.
- **A replay and scoring harness** for the test corpus: belongs with that
  comparison map. This version only has to record what a replay will need.
- **Writing the code.** This map ends at a plan.
- **Setting the monthly budget and its warning mark:** excluded from the first
  version by [What "done" means](issues/01-done-for-first-version.md); its
  behaviour is already fixed by the product spec, and metering keeps the
  month-to-date total it needs (see [Metering running cost](issues/12-cost-metering.md)).
- **Public-product concerns:** onboarding, billing, multi-tenant accounts.
