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

## Not yet specified

- **Tracking a candidate until its card.** How Carl notices the table settling
  a claim or open question (drop before the card, "Settled at the table" after),
  how in-flight checks run concurrently, and how a late card is filed. Hangs on
  the decision model's context and de-duplication.
- **Location.** How the phone's precise location reaches the stages (raw
  coordinates or a place name, via which service, how often updated), and how
  it is rounded to neighbourhood or town for the test corpus.
- **Development mode vs normal mode.** Whether the dev version is a separate
  deployment, a switch, or a URL, and how the recording-session disclosure and
  objection flow look on screen.
- **Can't-hear-or-check state.** Which signals from each stage flip the
  listening indicator, and what the failure log records per stage. Known
  signals so far: a dropped page–server connection, the 2-minute reconnect
  grace period, and a server restart.
- **Prompts and their one source of truth.** Where the decision,
  fact-finding and fact-checking prompts live, how card language is
  chosen for mixed Finnish/English talk.
- **The screen.** Turning the [fact card prototype](../purpose-and-goal/prototypes/fact-card-prototype.html)
  into the real UI: Start screen, budget warning, card archive view, "Log" menu.
- **Build order.** How the plan slices into implementation steps once the
  architecture is decided.

## Out of scope

- **The rigorous vendor and model comparison** against the test corpus
  (word error rate, speaker attribution, precision/recall per stage, cost): a
  later, separate map that consumes the recordings this version makes.
- **A replay and scoring harness** for the test corpus: belongs with that
  comparison map. This version only has to record what a replay will need.
- **Writing the code.** This map ends at a plan.
- **Public-product concerns:** onboarding, billing, multi-tenant accounts.
