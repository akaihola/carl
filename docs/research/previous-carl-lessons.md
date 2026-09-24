# Lessons from the previous Carl

What the first Carl implementation tried, what its commit history shows went
wrong or got tuned, and which lessons still hold for the clean-slate rebuild.
Compiled 2026-09-24 for
[.scratch/purpose-and-goal/issues/01-lessons-from-previous-carl.md](../../.scratch/purpose-and-goal/issues/01-lessons-from-previous-carl.md).

**Sources.** The primary source is the repository itself: the tree at
`36d60c3~1` (the last commit before "chore: clear all files for a clean-slate
ng implementation"), the full commit log (`git log 36d60c3~1`, 42 commits) and
the individual diffs. Citations below are commit hashes, or `path@36d60c3~1`
for a file in the final tree. The old code has no tests, issues or evaluation
data, so every "what went wrong" claim is inferred from commit messages and
code. No external sources were needed. Statements about how things have changed
since then are marked as judgement, not fact.

## At a glance

- **Lifetime.** One placeholder README (9d5323e, 2025-06-24), then all real
  work in three days, 2025-12-16 to 2025-12-18. It was a quick prototype,
  largely written by Claude Haiku 4.5 (per the co-author trailers), and was
  never evaluated against recorded conversations.
- **Shape.** A static web page (vanilla JS, no build, deployed to GitHub
  Pages: 9f21a8e) that opened a WebSocket straight from the browser to the
  Gemini Live API with the user's own API key held in `localStorage`
  (d02d6e6). There was no server.
- **Purpose drift.** It began as a general assistant that "contributes when
  appropriate" and in its last two days narrowed to a fact-checker that also
  answers open questions. That is roughly the purpose the rebuild now states
  in `AGENTS.md`.

## The purpose it pursued, and how that changed

### Phase 1: a talking assistant that "contributes when appropriate" (Dec 16–17)

`README.md@36d60c3~1` (never updated) describes the original idea: listen
through the microphone, show a live transcription "in subtitle style", feed it
often to an LLM "to generate textual contributions when appropriate", and show
those contributions as a large text banner. The page title stayed "Gemini
Live API – Minimal Client" to the end (`index.html@36d60c3~1`).

- 2f85241: a minimal Live API client with an editable system prompt ("You are a
  helpful assistant. Keep responses concise.").
- 7035865: switched to a native-audio Gemini 2.5 Flash model that **spoke its
  answers aloud** (voice "Kore") while the text showed on screen.
- b39a7ce: the prompt became "an assistant which contributes concisely to a
  conversation only when facts are needed". It had two notable rules:
  - **Grace period:** respond only after a need for a fact (a question,
    pondering, misinformation or incomplete information) *plus at least one
    more utterance which doesn't correctly provide the fact*. "Do NOT give a
    response with content immediately."
  - **Confidence protocol:** answer directly if at least 99% confident.
    Otherwise emit `§{"q":…,"a":…,"c":75}`, and the client sends the question
    to Gemini 2.5 Pro with Google Search and code execution for verification.
- e6f2b50: added the user's location, time zone and reverse-geocoded street
  address (through OpenStreetMap Nominatim) to the system prompt.

The subtitle transcript that the README promised was never built. The code
never requested input transcription, so the screen showed only the model's
output.

### Phase 2: a silent fact-checker with a verification queue (Dec 18)

7df78ba was the main architectural change. The live model (now
`gemini-2.0-flash-exp`, text output only) stopped answering. It only
*identified* facts, emitting numbered lines such as `Q1: How many moons does
Mars have?` / `A1: Mars has three moons`. The client parsed these silently
into a first-in, first-out queue, and Gemini 2.5 Pro with Google Search and
code execution checked them one at a time (`js/facts.js`, `js/response.js`).
The reply protocol was:

- `CORRECT`: the claim holds, so show nothing (0b44ff7 made sure of this).
- `SKIP`: the question is private, situational, opinion or cannot be answered,
  so it is dropped silently (60e7cd1).
- anything else: the correction or answer, streamed to the screen as a large
  banner.

1993fce added **open-question answering**: a `Q` with no `A` is sent in
"find the answer" mode. This is the direct ancestor of the rebuild's *open
question* trigger.

## What the commit history shows went wrong or got tuned

Each item gives the symptom, the fix, and what it tells us.

1. **The CORRECT verdict leaked onto the screen** (0b44ff7). The display
   started streaming before the first word was known, so "CORRECT…" could
   flash up. The fix buffered output until the first word was known and then
   deleted any displayed text. *Lesson:* a silent outcome must never reach the
   screen. That needs a structured verdict decided **before** anything
   renders, not first-word sniffing of a text stream.
2. **Completed facts were shown again and again** (a008d38). The live model
   restated old `Q1`/`A1` lines in later turns and each restatement re-queued
   the fact ("Q1 keeps repeating"). The fix was a permanent `completed` set.
   *Lesson:* letting a stateful live model assign and reuse IDs is fragile.
   Deduplication has to live in Carl's own state, keyed on the claim, not on
   model-chosen numbers. There was also a side effect: once a fact was
   completed, a later self-correction by the speaker was ignored.
3. **Answer changes during verification** (61aa087; example: "Mikä on Suomen
   pääkaupunki?"). If the conversation revised an answer while Pro was still
   checking it, the old result was shown. The fix re-queued the fact and
   suppressed the stale result. *Lesson (durable):* the conversation keeps
   moving while a check runs. A verdict should be dropped if the table has
   already corrected itself or moved on.
4. **Questions were never queued unless an answer arrived** (e5d032c), then
   questions were queued immediately (1993fce). *Lesson:* this is where the
   open question as a trigger in its own right was born.
5. **Chunked output split mid-line** (92085a7): "Q1: Mik" + "ä on Suomen
   pääkaupunki?" was stored as the question "Mik". The fix was line buffering.
   *Stale:* an artifact of parsing a free-text protocol from a stream.
6. **Short answers were never displayed** (60e7cd1). The display heuristics
   waited for a space or 10 characters. *Stale:* the same first-word-sniffing
   problem as item 1.
7. **Context-free, truncated answers** (60e7cd1, 0b44ff7). "Helsinki" instead
   of "The capital of Finland is Helsinki", and truncation at 1024 tokens. The
   fixes were prompt examples and 2048 tokens. *Lesson (durable):* the card is
   read out of context, seconds later, by people who may not recall the
   sentence. It must stand alone. That is why the rebuild has a separate
   message-writing model and a fixed title / one-sentence fact / source shape.
8. **Unanswerable questions** (private, situational, opinion,
   context-dependent) needed filtering (60e7cd1). It was done twice: in the
   primary prompt and as a `SKIP` fallback. *Lesson (durable):* much of what
   people ask at a table is not a checkable fact ("how old is my sister?",
   "what should we order?"). The decision model must reject these.
9. **The live model went quiet during pauses** (9d17632). The fix sent a
   zero-filled audio frame every second. A local RMS voice-activity gate had
   also been added to save bandwidth (f718ff0). *Stale:* this worked around
   one API's turn detection.
10. **Hidden "thought" parts showed up as responses** (213eb54). *Stale.*
11. **The screen locked mid-conversation** (92380ed). The fix was the Screen
    Wake Lock API. *Durable:* this is in the new research too.
12. **Display tuning** (7856d5f, 0e042e6, b516c2b, 2c57dca, 7b6d89a, 73b703b).
    Six commits went into binary-search font sizing so each banner filled the
    viewport, into word-break rules and into smooth scrolling. *Mixed:* the
    goal of big text readable across a table still holds. Streaming text
    progressively and resizing it on the fly does not fit a short fact card
    that appears whole.

## Problems in the final code that no commit acknowledged

These come from reading the final tree. The code probably behaved this way,
but it was never confirmed by running it.

- **The primary prompt with the filters was dead code.** `connection.js` reads
  the system prompt from the `<textarea>` in `index.html`
  (`ui.getSystemPrompt()`). That textarea holds a *shorter* prompt without the
  private/situational/opinion skip list. `config.PRIMARY_SYSTEM_PROMPT`, which
  has the list, is referenced nowhere. Only the verifier's `SKIP` fallback
  actually filtered. The grace-period rule from phase 1 survives only as an
  HTML comment. *Lesson:* keep one source of truth for prompts, and test them
  against recorded examples.
- **There was no confidence gate on what was shown.** Phase 1 had a 99%
  threshold. In phase 2, everything Pro returned that was not
  `CORRECT`/`SKIP` went on screen, including hedged, partial or "it depends"
  answers. Nothing in the protocol let the verifier say "not sure". This
  breaks the rebuild's rule "never surface uncertain verdicts".
- **Every claim was re-checked.** The primary prompt turned every claim into a
  `Q`/`A` pair. Answering open questions immediately meant a question the
  table then answered itself could still get a card, because the phase-1
  grace period was gone.
- **Errors went on the card.** A failed request rendered
  `[Verification failed: …]` as a banner. For a precision-first display,
  failures should be silent (logged, not shown).
- **Any text from the primary model that was not in fact format was shown
  directly** (`processTranscription` → `updateText`). A chatty reply from the
  identifier would leak to the screen.
- **The card never showed a source.** Grounding metadata was only logged to
  the console. The teal "grounded" border in `styles.css` was the only hint.
- **Speakers were not identified.** Raw audio went to one live model, so
  there was no speaker attribution, no final-utterance boundary and no
  transcript Carl owned. The model's "turn complete" signal was the only
  unit.
- **Only one check at a time.** The queue ran strictly in order with one
  request in flight, so a slow Pro search delayed every later card.
- **Leftover assistant behaviour:** pressing Enter sent "Tell me another
  intriguing fact." (`main.js@36d60c3~1`). The live session also had no
  handling for session length limits or reconnects. (Whether the API had such
  limits at the time was not checked here.)
- **Privacy:** the precise street address went into every system prompt and
  coordinates went to a third-party geocoder. That was never weighed against
  the benefit.

## Which lessons still hold

### Durable: purpose and user experience

1. **Silence is the default output.** The history is a sequence of commits
   that made Carl show *less*: hide CORRECT, drop SKIP, stop re-showing
   completed facts, drop stale results. This supports "precision over
   recall", and it should be designed in from the start rather than patched
   in.
2. **Two triggers, not a general assistant.** Carl moved on its own from
   "contributes when appropriate" (and speaking aloud) to exactly two
   triggers: a wrong claim, and a question the table can't answer. The speech
   output and the "intriguing fact" behaviour were dropped. That supports the
   current working hypothesis in the map.
3. **Correct claims produce nothing.** A confirmation is noise. (Whether a
   quiet "✓" has any value is a question for *Edges of the purpose*, but the
   previous Carl's answer was no.)
4. **Give the table a chance first.** Phase 1's rule "wait for at least one
   more utterance that doesn't provide the fact" is the right instinct for
   open questions, and it is lost in phase 2. A card that pre-empts someone
   who was about to remember the answer is rude. This needs to be an explicit
   part of the spec (a grace period or "still unresolved" check).
5. **Drop verdicts overtaken by the conversation.** If someone corrects
   themselves, or the answer is found while the check is running, show
   nothing (61aa087, a008d38).
6. **Cards must stand alone** (full sentence, context included) and be
   **readable across a table** (large type, screen kept awake).
7. **Filter what is not checkable:** private, situational, opinion,
   context-dependent. This belongs in the decision model, backed by a check in
   the fact-checking model.
8. **The conversation may be in Finnish.** The only real examples in the
   history are Finnish ("Mikä on Suomen pääkaupunki?"). The spec should state
   which languages are expected. This affects speech-to-text choice and card
   language.
9. **"Just open a web page" worked.** A static page with no install, deployed
   to Pages, was enough for personal use. That matches the requirements in
   `AGENTS.md`.

### Probably stale: tied to specific models, APIs or workarounds

- The specific models (`gemini-2.0-flash-exp`, the Dec-2025 native-audio
  preview, `gemini-2.5-pro`). Choosing models is out of scope for this map,
  and the landscape has moved (see `realtime-fact-checking.md`).
- The single audio-understanding live model that doubled as speech-to-text
  and decision model. The rebuild splits speech-to-text with diarization from
  a text-only decision model that runs on final utterances. That removes the
  model-numbered Q/A protocol, the chunk parsing, the "thought" filtering and
  the missing speaker attribution.
- Keeping the Live API awake with silence frames, and the hand-rolled RMS
  voice-activity gate.
- The `CORRECT`/`SKIP` first-word text protocol. It should be replaced by a
  structured verdict (outcome, answer, source, confidence) as `CONTEXT.md`
  already defines.
- Streaming the verifier's prose directly to the screen, and the font-size
  work built around it.
- Browser holds the API key and calls the vendor directly. This may still be
  acceptable for private use, but it is an implementation choice, out of
  scope here.
- Location injection. It may still help with "here/now" questions, but the
  implementation (street address in the prompt) and its privacy cost belong
  to the *Privacy beyond "in memory only"* note in the map, not to the
  purpose.

## Implications for the purpose spec

- Keep the two triggers. Record "no confirmations, no spoken output, no
  general chit-chat" as deliberate non-goals. The previous Carl tried those
  things and dropped them.
- Add an explicit **grace period / still-unresolved** rule for open questions,
  and a **supersede** rule (drop a verdict the conversation has overtaken).
- Make **"never show an error or a hedge"** part of how success is judged,
  alongside "never show a wrong correction".
- Set the **language(s)** expected at the table.
- Success must be measured on recorded conversations. The previous Carl was
  tuned on anecdotes over three days and had a prompt silently not in use.
