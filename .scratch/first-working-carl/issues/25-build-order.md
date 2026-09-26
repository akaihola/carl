# Build order

Type: grilling
Status: resolved
Blocked by: 20, 23, 24

## Question

How does the decided plan slice into implementation steps, from a skeleton
that records a session end to end towards the full first working version?
Which steps come first so real dinners can be recorded as soon as possible,
what is checked early (e.g. the ~50 min WebSocket handover, the Perplexity
test call, Soniox Finnish), and what does each step leave working?

## Answer

Settled with the owner in a grilling session (2026-09-26), two rounds, every
recommendation accepted.

**Ground rules**

1. **Record dinners before cards are live.** Recording starts at the recorder
   step (step 2), once the disclosure screen, the recording mark and the
   one-way stop-and-delete work. These dinners are audio for later replays,
   not tests of Carl's cards; the config and commit each recording already
   stores show which stages were off.
2. **A step is done** when (a) pytest passes on the pure logic with fake
   adapters (utterance splitting, backchannel skip, repeat and candidate
   thresholds, bands, the late-card cut, cost maths), run by GitHub Actions
   on push to `main`, with no live provider calls in CI; and (b) the step is
   deployed and used for one session on the phone: a real dinner, or a
   Finnish radio talk show playing beside it.
3. **Dev file source:** a local-only way to send an audio file over the
   WebSocket instead of the mic, as a development aid. It is not the replay
   and scoring harness, which stays out of scope.
4. **The page** is plain HTML, CSS and JS modules, no build step and no
   framework, served by the Python server; the AudioWorklet is its own small
   JS file; Atkinson Hyperlegible is self-hosted, so the page makes no
   third-party calls.
5. **The order stops at "done".** `spec.md` lists what
   [What "done" means](01-done-for-first-version.md#answer) left for later
   (settled mark, live transcript line, Log menu, 30-min silence end, card
   archive, budget setting) as the next version's scope, unordered.
6. **Fact-finder B's fallback,** if Gemini 3.8 Flash on Perplexity fails the
   smoke test: another non-OpenAI model on Perplexity's Agent API with its
   `web_search`; as a stopgap, fact-finder A alone (hedged cards only).
7. **Implementation tickets:** `spec.md` gets a Build order section with the
   steps below, their checks and what each leaves working. When coding
   starts, each step becomes one ticket in a new `.scratch/<build-effort>/`
   folder, split there if too big for one agent session. This map creates
   none.

**Early checks and what they gate**

| Check | When | Gates / fallback |
| --- | --- | --- |
| Luna + OpenAI web search (Responses API, effort `none`, `tool_choice: required`, JSON) | Step 0 | Fact-finder A; fallback Luna on Perplexity |
| Gemini 3.8 Flash + `web_search` + JSON schema on Perplexity's Agent API | Step 0 | Fact-finder B; fallback in rule 6 |
| TypeSafe Jev typed answers with probabilities, in Finnish | Step 0 | Fact-checking; fallback Gemini 3.5 Flash-Lite |
| 2-hour WebSocket through Cloudflare's proxy to the container: real cut, CPU throttling with no page, cold start | Step 1 | Handover design; Instance fallback ([ADR 0002](../../../docs/adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md)) |
| Android Chrome for 2 h: AudioWorklet at 16 kHz, wake lock, mic kept, heat and battery | Step 2 | The page |
| Soniox at a real table: Finnish, code-switching, diarization at 1–2 m | First recorded dinner | Nothing; tells early how good it is |
| Owner reads OpenAI's and Perplexity's legal terms (HITL) | Before the first dinner with fact-finders (step 4) | Keeping search results in recordings |

**The steps**

0. **Provider smoke test** (local, throwaway script, FI and EN inputs).
   *Leaves:* each text stage's provisional model confirmed or its fallback
   chosen. Nothing is built until this is settled.
1. **Skeleton in the cloud:** Python server and page shell from
   drum-transcribe's pieces (access-pass gate, loading Worker, Dockerfile,
   deploy commands); the bucket with its 180- and 30-day rules; the config
   file and `prompts/` folder; pytest in GitHub Actions; a WebSocket with a
   heartbeat; then the 2-hour connection test. *Leaves:* `faktat.vempai.men`
   opens behind a pass; the real cut, throttling and cold start are known.
2. **Recorder:** AudioWorklet mic → server → Soniox; utterance splitting;
   audio chunks and the JSONL event log in `recordings/<id>/` with the
   config, prompts and commit snapshot; Start screen with the Record switch
   and costs, disclosure screen, Listening and Recording pills,
   stop-and-delete, Pause, End, wake lock; the 2-minute reconnect grace;
   speech-to-text cost metering and the month's total; the owner script's
   `list / fetch / delete`; the dev file source. *Leaves:* recorder-only
   dinners.
3. **Decision model:** decision calls with context, the backchannel skip,
   repeats, card language, location (`watchPosition` + Nominatim).
   Candidates recorded, not shown. *Leaves:* dinners record what Carl would
   have checked.
4. **First cards:** fact-finder B (A if B failed the smoke test), excerpt
   verification, blocklist, fact-checking verdicts, hedged cards only; the
   session screen (top bar, current card, card history, pacing, late-card
   cut). *Leaves:* cards live at the table.
5. **Second fact-finder:** the parallel pair, the ~12 s wait, A's page
   download, the agreement call and the plain band. *Leaves:* the full
   confidence split.
6. **Tracking candidates:** the settle call with the drop rule (the mark is
   later), the cap of 8, the 60 s timeout, cards re-sent after a reconnect.
7. **Robustness:** can't hear / can't check, the failure log (server entries
   and the page's buffer), resume from `state.json`, the gapless ~50-min
   handover, Soniox reopen with backoff and rotation. Until this step, the
   60-min cut is covered by the reconnect grace, losing a second or two of
   audio marked as a gap.
8. **Corpus and costs:** `generate / put / check` (run then over every dinner
   so far), the per-session cost summary and the Start screen's last-session
   line.
9. **Acceptance:** one 2-hour recorded dinner runs end to end: **done**.

No ADR and no new domain terms: the order is a plan for the work, cheap to
change as the checks report.
