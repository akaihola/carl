# Prior art: live fact-checking and question answering on spoken conversation

Research for the ticket *Prior art in live conversation fact-checking*
(`.scratch/purpose-and-goal/issues/02-prior-art.md`), compiled 2026-09-24.
Complements [realtime-fact-checking.md](realtime-fact-checking.md), which
covers architecture and the speech-to-text and decision-model vendors. This
note covers scope and behaviour: what comparable systems show, when they show
it, and how they avoid showing something wrong.

## How this was researched, and how far to trust it

- The network proxy in this session blocked direct page fetches from arXiv,
  ACM, Google, vendor sites and news sites. Claims marked **[search]** come
  from search-engine summaries of the cited page, not from reading the page
  itself. Check them against the source before relying on them.
- GitHub was reachable. Claims marked **[code]** were read directly from the
  repository at the stated commit date and are first-hand.
- **[vendor]** marks self-reported product claims with no independent
  measurement.
- Studies of how people feel about being corrected by a machine are left out
  on purpose (see the map's *Out of scope*).

## Summary

1. **Nothing shipped does exactly what Carl does.** Carl is an ambient,
   in-person, general-knowledge fact-checker for a private table. The closest
   products are smart-glasses "conversation cue" features (Even Realities
   Conversate, Halo X) and meeting copilots (Cluely and its clones). None
   publishes how it decides to show a fact-check or how accurate it is.
2. **The systems that do publish their error control are broadcast and
   livestream tools**: Full Fact, Duke's Squash, Factiverse/LiveFC and the
   open-source Footnote. They all keep a **human in the loop**, or earn
   autonomy one category at a time. The main machine-only safeguards are:
   - **matching against claims already checked** (Full Fact, Squash);
   - **two independent verifiers that must agree** (Footnote);
   - **a confidence floor**, which only means something after it is
     calibrated;
   - **hard "never auto-show" classes** (claims about people, quotes, claims
     with an unresolved referent);
   - **"Unverifiable" as the default verdict**.
3. **An LLM's self-reported confidence is not a usable threshold on its
   own.** Two independent projects measured this: one found saturated
   confidence of 0.97–0.99 even on wrong verdicts, the other found quantized
   judge scores. Footnote's confidence only started separating right from
   wrong once it took the minimum of two verifiers.
4. **The known ways a spoken claim goes wrong** are ASR errors, claims spread
   across turns and speakers, and pronouns whose referent falls outside the
   context window. Footnote aired a wrong card because "it" was resolved to
   the wrong thing. This matters for Carl's rule to keep the decision model's
   context short.
5. **Precision-first has a known failure on the other side.** Google's Magic
   Cue barely appears (about 70% of 9to5Google poll respondents said "it
   hardly shows up"), and users read that as the feature not working. Carl
   should expect this and make it visible that it is listening.
6. **Research on proactive assistants frames the problem the same way Carl
   does**: speaking and staying silent have asymmetric costs. PRISM gates on
   a calibrated threshold derived from those costs and runs slow deliberation
   only near the boundary. EgoSocial found that frontier models are still
   poor at choosing *when* to step in.

## Landscape at a glance

| System | Setting | What it surfaces | Trigger | Error control |
| --- | --- | --- | --- | --- |
| Even Realities G2 *Conversate* | Glasses, in person | "AI Cues": definitions, bios, fact-checks, suggested answers | Automatic, from live audio | Not published [vendor] |
| Halo X (Halo, 2025) | Glasses, always listening | Real-time info from Gemini and Perplexity | Automatic | Not published [vendor] |
| Brilliant Labs Halo / Noa | Glasses | Memory recall ("Narrative") | Mostly asked | Not published [vendor] |
| Google Pixel Magic Cue | Phone, calls and chats | Personal info (flight number, booking) | Automatic, on device | Very conservative; rarely appears |
| Gemini Live API *proactive audio* | Voice-agent API | Spoken reply | Model decides whether to speak | Not published; preview |
| Cluely / Natively | Desktop meetings | Answers to detected questions, "fact checks" | Cluely: question detection, user pulls the answer. Natively: a judge | Natively: tiered thresholds by mode [code] |
| Visual Captions / ARChat (Google, CHI '23) | Video calls | Images and emoji for spoken concepts | Continuous (every 100 ms on the latest sentences); 3 proactivity levels | Duplicate suppression; user choice of level [code] |
| Memoro (MIT, CHI '24) | Wearable audio | The user's own memories | User invokes; the system infers the query | User controls timing |
| Inner Thoughts (CHI '25) | Multi-party chat | Agent contributions | Intrinsic-motivation score | Score threshold |
| ChatMuse (UIST '26) | Mixed reality, small group in person | Private guidance | Proactive | Research prototype |
| Full Fact live | Broadcast | Human-written checks | Humans; AI flags repeated claims | Claim matching and editors |
| Squash (Duke) | Broadcast | Previously published fact-checks | Match to the ClaimReview corpus | Human picks from 3 matches ("Gardener") |
| Factiverse Live / LiveFC | Debates, podcasts | Claim, verdict and evidence per speaker | Check-worthiness classifier | Human fact-checkers review |
| Footnote (open source) | Livestream | Verdict lower-third | Haiku extraction, then Perplexity verification | Operator; earned auto-air; concurrence |

## In-person and ambient assistants (closest to Carl)

### Even Realities G2: Conversate [vendor][search]

- Listens through the microphone only; the glasses have no camera. It shows
  "AI Cues": concept explanations, background on people, suggested answers,
  recommended actions, and "live fact checks on names, claims, or places",
  followed by a summary after the conversation.
- The March 2026 update added **Prep Notes**: the user uploads documents
  before a meeting, and cues are then grounded in them.
- Reviewers present it as a trivia-night aid and a way to "call someone out on
  their nonsense". A Tom's Guide writer "fact-checked my boss".
- No thresholds, cue frequency or accuracy figures are published. The
  support-page details could not be fetched.
- **For Carl:** the one shipped consumer product with the same trigger set
  (fact-check plus answer). Its scope is much wider (bios, definitions,
  suggested replies), which is the opposite of Carl's narrow two-trigger
  scope.

### Halo X (Halo, 2025) [vendor][search]

- $249 always-listening glasses that "listen, record, and transcribe every
  conversation and then display relevant information… in real time". They use
  Gemini for reasoning and Perplexity for web lookup. Coverage centred on
  privacy concerns, not accuracy.
- Do not confuse it with **Brilliant Labs Halo** ($299, "Noa" assistant,
  "Narrative" memory). That product answers questions when asked and recalls
  the user's own life. It is not a fact-checker.

### Google Pixel Magic Cue (2025–) [search]

- An on-device Gemini Nano feature that shows personal information in context,
  for example the flight number when you call an airline.
- In practice it almost never appears. About 70% of respondents to a
  9to5Google poll said "it hardly shows up", and Android Authority called it
  "really bad" after a month of use.
- **For Carl:** a live example of precision-over-recall pushed so far that
  the feature seems absent. A silent Carl looks broken unless it shows
  somehow that it is listening.

### Gemini Live API: proactive audio [search]

- A preview flag (`proactivity: { proactiveAudio: true }`) on native-audio
  models. The model "decides not to respond" to input that is not relevant and
  acts as "a silent co-listener". Google's example: two people talk and the
  agent answers only when addressed.
- Output tokens are billed only when the model speaks. It is not supported on
  Gemini 3.1 models.
- **For Carl:** a candidate way to merge the decision model and speech-to-text
  into one stage. It hides the decision, though, and gives no confidence to
  put a threshold on.

### Memoro (MIT Media Lab, CHI 2024) [verified]

- A wearable audio memory assistant. In **Queryless mode**, the user signals
  that they need help, and an LLM "query agent" infers the memory need from
  the conversation. A retrieval agent then answers through bone conduction.
  Suggestions are deliberately minimal.
- Of 20 participants, 15 preferred Memoro over both no system and a
  non-context-aware LLM baseline, and 10 preferred Queryless mode. Using it
  cut device interaction time and preserved conversation quality.
- Queryless mode inferred the right need 70.7% of the time; errors were
  "due to the Query Agent misinterpreting the context".
- **For Carl:** the nearest research analogue to the *open question* trigger.
  Note that the **human chooses the moment** and the system only works out
  *what* is needed. Carl tries to infer both, which is harder.

### Visual Captions / ARChat (Google, CHI 2023) [verified][code]

- A fine-tuned LLM proposes images for what is being said in a video call,
  querying the latest captions every 100 ms. There are three proactivity
  levels: **auto-display**, **auto-suggest** (shown in a private view; the
  user clicks to share it) and **on-demand-suggest** (suggests only when the
  user presses the spacebar). "Different levels of AI proactivity in Visual
  Captions were preferred in various social scenarios"; in the lab study 6
  participants preferred auto-display, 7 auto-suggest and 7 on-demand.
- In the open-source ARChat code (`github.com/google/archat`), a new
  suggestion is dropped if its entity name has Jaccard similarity above 0.7
  with a visual already on screen, after removing stopwords and punctuation.
  This is dedupe by topic.
- **For Carl:** a precedent for making proactivity a setting, and for simple
  text-similarity dedupe.

### Inner Thoughts (CHI 2025) and ChatMuse (UIST 2026) [verified]

- *Inner Thoughts* generates a parallel stream of candidate "thoughts" and
  voices one only when its intrinsic-motivation score is high enough,
  combined with a turn-taking prediction. The
  heuristics come from a 24-person study of when humans hold back. It beat
  next-speaker-prediction baselines on turn appropriateness and related
  measures.
- *ChatMuse* is a mixed-reality agent for small groups in person. It reads
  verbal and non-verbal cues and gives the user private, real-time guidance
  on their own verbal and non-verbal behaviour (Meta Quest Pro study, 6
  groups, N=18).
- **For Carl:** separating "generate a candidate" from "decide whether to
  speak" matches Carl's split between decision model and fact-checking model.

## Meeting copilots

### Cluely [vendor][verified]

- An overlay that listens to calls and shows a Live Insights card with
  "Dynamic Insights": questions, keywords and suggestions detected from the
  transcript. The user clicks one, or presses Tab to answer the top "Dynamic
  Action". The docs list "Fact check" as a one-click default action.
- Journalists' tests in April 2025, before the current Live Insights UI,
  reported delays of 5–90 s and generic suggestions.
- **The answer is user-pulled.** Detection only offers a prompt; it does not
  push an answer.

### Natively, an open-source Cluely alternative [code, commit 2026-09-24]

The only copilot whose trigger logic is public. Relevant parts:

- **Three outcomes, not two.** A judge LLM scores how answerable a question
  is. Above `autoThreshold` the answer fires automatically; above
  `offerThreshold` an offer card appears that the user clicks; otherwise
  nothing happens.
- **Thresholds scale with who else can see the screen.**

  | Mode | Auto | Offer |
  | --- | --- | --- |
  | Interview (user alone) | 0.88 | 0.65 |
  | Meeting ("colleagues present; fire less, offer more") | 0.94 | 0.75 |
  | Lecture | 0.97 | 0.80 |

  All are marked "unfitted placeholders". Source:
  `electron/context-intelligence/policies/mode-policy-registry.ts`.
- **The judge's confidence is quantized.** Across all captured sessions the
  judge returned only 0, 0.1, 0.4, 0.8, 0.9 and 1.0. The one bad answer came
  from the 0.4 band. Source: `electron/intelligence/autoAnswer/SimpleAutoAnswer.ts`.
- **When it runs:**
  - It is called once per **stoppage**: speech must stay quiet for 900 ms, or
    350 ms after the STT provider marks an endpoint. It is never called on
    every final segment; an earlier version judged one utterance six times.
  - Backchannel-only turns ("yeah", "mm-hm", "right") and turns with fewer
    than 4 new words are dropped before any LLM call.
  - A judge call still running is dropped when new speech arrives.
- **Rate limiting:** at most one prefetch per 25 s. Duplicate actions within
  2 minutes are suppressed, and actions expire after 60 s.
- **For Carl:** a working template for "decide on a pause, not on every
  final", a cheap prefilter before the decision model, and the offer tier.
  The measured score quantization is a warning against fine-grained
  confidence thresholds.

## Broadcast and livestream fact-checking (for their error control)

These are not conversational, but they are the only systems that publish how
they avoid false corrections.

### Full Fact (UK) [verified]

- A team of "normally at least four people, sometimes as many as 10"
  fact-checks live. At least two editors work alongside them, deciding what
  to write up and reviewing copy before it goes out; everything published
  "normally has at least two additional pairs of eyes on it".
- Their AI provides the transcript and **flags repeated claims**: claim
  matching compares what is said with claims Full Fact has already checked.
  Plain embedding similarity "confused different people or places", so they
  added entity recognition, a part-of-speech tagger and a trained match
  classifier, and later a generative model.
- **For Carl:** matching against known false claims is the highest-precision
  pattern that exists, but it covers only claims someone has already checked.
  Embeddings alone confuse entities.

### Squash (Duke Reporters' Lab, live tests 2019–2021) [verified]

- Speech-to-text, then ClaimBuster, then a match against published ClaimReview
  fact-checks, shown as a pop-up.
- Lessons they published:
  - The pop-up must say it is a **"related fact-check"**, not a verdict on
    the exact sentence.
  - Coverage depends on a large corpus of earlier checks.
  - The "Gardener" interface was added so a human could choose among 3
    candidate matches, or reject them all, before anything aired.

### Factiverse Live and LiveFC (WSDM 2025) [verified]

- The pipeline:
  - diarization, so claims are tied to a speaker;
  - a fine-tuned XLM-RoBERTa-Large check-worthiness classifier (macro-F1
    0.899 against 0.695 for GPT-4);
  - claim normalization, whose prompt asks the model to "resolve any
    references to pronouns, dates, and other entities" (compare Footnote's
    referent failure below);
  - evidence retrieval from Google, Bing, Wikipedia, You.com, Semantic
    Scholar and a corpus of 280K fact-checks;
  - a binary NLI verdict (supported or refuted) per evidence snippet,
    combined by majority vote.
- Piloted live by the Danish fact-checkers Tjekdet on European Parliament
  election debates in June 2024. Evaluated on the first 2024 US presidential
  debate against PolitiFact: it found all 30 claims PolitiFact checked, with
  macro-F1 83.92 on their verdicts.
- Tjekdet's editor-in-chief, quoted on Factiverse's blog, said the transcript
  was "almost 95%" accurate and that the tool picked up claims their
  5-person team missed [vendor].

### Footnote (open source, `github.com/jordanpeele/footnote`) [code, Aug 2026]

A livestream fact-checker built on Deepgram, Claude Haiku (extraction) and
Perplexity sonar-pro (verification). Its editorial policy
(`HOW_FOOTNOTE_DECIDES.md`) and calibration reports are the most detailed
public record of precision engineering on live speech. All figures below are
self-reported by the project on its own golden sets.

- **Scope of a checkable claim:**
  - checked: atomic, factual, falsifiable, verifiable by a third party;
  - excluded: opinion, predictions, hyperbole, personal experience ("I grew
    up poor") and claims too vague to pin down.
- **The extraction stage is deliberately recall-biased** ("when in doubt,
  EXTRACT"), and precision is enforced downstream. This is the same split as
  Carl's decision model and fact-checking model.
- **Five verdicts:** True, False, Misleading, NeedsContext and Unverifiable.
  *Unverifiable is the honest default*, and any malformed verdict becomes
  Unverifiable.
- **Evidence floor:** a definitive True or False needs primary or wire
  sources, or two independent established sources. Social media, forums and
  blogs can never be cited.
- **Classes that never auto-air**, whatever the confidence: claims about
  named living people, quote attributions, and claims led by a bare pronoun
  (`suspect_referent`). The pronoun rule came from a real failure. "Donald
  Trump carried it three times" was extracted without its referent (Ohio),
  the verifier took "it" to mean the presidency, and a wrong **False** card
  aired.
- **Concurrence:** two independent verifier arms must both return the same
  definitive verdict, and confidence is the minimum of the two arms. The
  project reports:
  - precision in the auto-air population of 96.8% (209/216);
  - mean confidence of 0.95 when right and 0.60 when wrong, where the two had
    been only 0–2 points apart with one verifier;
  - raw single-model confidence "saturated (0.97–0.99 on nearly everything,
    including the one wrong card ever aired)";
  - residual errors from both engines "sharing cultural priors" and
    over-committing on nuance (Misleading claims called False).
- **Autonomy is earned by category.** Auto-air is allowed only in categories
  with at least 30 scored cases and at least 95% precision at the 0.85 floor.
  Only `science_health` has qualified so far. There is a session cap of 10
  auto-airs, and a latch revokes auto-air after the first wrong machine-aired
  card about a person.
- **Display pacing:** each card stays at least 6 s. The queue holds at most
  8, and the oldest is dropped when it is full. Claims are deduped within
  60 s.
- **Speaker attribution:** a claim is attributed only when one diarized
  speaker owns at least 80% of its words, because "a wrong name… is worse
  than no name".

## Research datasets on spoken-dialogue fact-checking [verified]

- **MAD** (arXiv 2508.12186, SBP-BRiMS 2025 working paper): multi-turn audio
  dialogues with check-worthiness labelled per sentence, and veracity
  labelled per sentence and per dialogue. Verification accuracy is only about
  72–74% per sentence and 71–72% per dialogue for fine-tuned RoBERTa-base,
  DeBERTa-v3-base and Llama 3 8B.
- **MAD2 / context-aware verification** (arXiv 2606.11420, June 2026; v2
  accepted to the SALMA workshop at EMNLP): 1,000 synthetic two-speaker
  dialogues (about 10 h of audio) with 1,230 sentence-level check-worthy
  candidates (v1 reported 3,368 claims). Dialogue context helps. "Past-only
  context often approaches local offline performance", which supports live
  use.
- **TRILOGUE** (arXiv 2609.04452, Sep 2026, to appear at EMNLP 2026): nearly
  12K dialogues in English, Russian and Kazakh with 390 h of audio. Claims
  are spread across speakers and turns. ASR errors and the lower-resource
  language (Kazakh) hurt verification, and retrieved evidence "substantially
  narrows the gap" to gold evidence.
- **Podcast fact-checking** (arXiv 2502.01402): on a small podcast test set
  (24 check-worthy of 176 sentences), F1 on the check-worthy class is only
  0.57 for few-shot GPT-4 against 0.45 for fine-tuned XLM-RoBERTa-Large.
  Overall weighted F1 is 0.85–0.86. The paper makes no comparison with
  debates, but finding the few check-worthy sentences in casual speech is
  clearly the hard part.
- **TREC 2025 Tip-of-the-Tongue track** (arXiv 2601.20671): known-item
  retrieval from vague descriptions ("that actor who…"). 2025 went beyond
  the 2024 movie, celebrity and landmark domains to 53 entity types. The
  best of 32 runs reaches nDCG@10 of about 0.66 (MRR about 0.63), and most
  score far lower. This is the closest benchmark for Carl's *open question*
  trigger.

## Proactive-agent research on when to speak [verified]

- **ProactiveBench / Proactive Agent** (arXiv 2410.12361) adds a
  *false-alarm rate* metric for unneeded interventions.
- **PRISM** (ICLR 2026, arXiv 2602.01532) intervenes only when the calibrated
  probability of the user accepting exceeds a threshold derived from the
  costs of a false alarm and of missed help. It runs a slow "counterfactual"
  mode only near the boundary. It reports about 23% fewer false alarms and
  about +20 F1 points (66.5 → 86.6) on ProactiveBench.
- **EgoSocial** (arXiv 2510.13105): omnimodal LLMs detect the right moment to
  intervene in egocentric social video poorly (14.4% for Gemini 2.5 Pro).
- **Sensible Agent** (Google, UIST 2025) chooses both *what* to help with and
  *how*, using minimal cues and subtle confirmation (head and hand
  gestures). In a 10-person study it lowered perceived effort and was
  preferred over a voice-prompted baseline, though interactions took longer
  (28.5 s against 16.4 s).

## Patterns relevant to Carl's purpose

Observations to feed into the purpose and spec tickets. They are not
decisions.

1. **Scope.**
   - Commercial ambient products surface far more than Carl plans to:
     definitions, bios, suggested replies, summaries.
   - Every system that publishes its error control narrows scope instead.
     They exclude opinion, prediction, hyperbole, personal experience and
     vague claims, and they hold back claims about named people and quotes.
   - Carl's two triggers already sit at the narrow end. Personal anecdotes
     and claims about people at the table are natural exclusions to record
     explicitly.
2. **Where precision comes from.** In the published records it comes from:
   - structure: a recall-biased decision stage, then a strict verifier that
     defaults to "unverifiable";
   - agreement: two verifiers, or a match to a known check;
   - never-show classes;
   - calibrated floors earned one category at a time.

   It does not come from trusting a single model's confidence.
3. **Context.** Keeping context short is right for cost. Both the
   dialogue-verification research and Footnote's referent failure show,
   though, that a claim can depend on earlier turns. A claim whose subject is
   a bare pronoun or is unresolved should not produce a card.
4. **Timing.**
   - Fire when speech pauses, not on every final segment.
   - Filter out backchannel and very short turns before any model call.
   - Drop in-flight work when newer speech supersedes it.
   - Pace cards: a minimum time on screen, a bounded queue and topic dedupe.
5. **Proactivity level.** Every conversational system offers or studies
   steps between "push" and "pull": auto-display versus auto-suggest in
   Visual Captions, auto versus offer in Natively, the human choosing the
   moment in Memoro. Carl currently assumes push only.
6. **The silence problem.** Magic Cue shows that "when unsure, show nothing"
   can read as broken. A spec should say what Carl shows while it is
   listening but has nothing to show.
7. **Open questions are the weaker-studied trigger.** No shipped system
   publishes how it detects "we're trying to remember X". Memoro sidestepped
   detection, and tip-of-the-tongue retrieval is still far from solved.

## Sources

Ambient and in-person assistants:

- Even Realities Conversate: https://support.evenrealities.com/hc/en-us/articles/14273795154319-Conversate ;
  https://www.evenrealities.com/ai-glasses ;
  https://tools.prnewswire.com/en-us/live/20823/release/20260326EN16415 ;
  https://www.tomsguide.com/computing/smart-glasses/i-fed-my-tamagotchi-looked-like-a-d1-athlete-and-fact-checked-my-boss-my-time-with-even-g2s-secret-smart-glasses-app-store
- Halo X: https://techcrunch.com/2025/08/20/harvard-dropouts-to-launch-always-on-ai-smart-glasses-that-listen-and-record-every-conversation
- Brilliant Labs Halo: https://brilliant.xyz/products/halo ; https://www.hackster.io/news/brilliant-labs-unveils-the-halo-smart-glasses-with-narrative-ai-and-vibe-mode-9755a165531d
- Magic Cue: https://support.google.com/pixelphone/answer/16508057 ;
  https://9to5google.com/2025/11/18/poll-do-you-notice-google-pixels-magic-cue/ ;
  https://www.androidauthority.com/google-pixel-10-magic-cue-one-month-later-3598684/
- Gemini proactive audio: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/proactive-audio ;
  https://ai.google.dev/gemini-api/docs/live-api/capabilities
- Memoro: https://arxiv.org/abs/2403.02135 ; https://dl.acm.org/doi/10.1145/3613904.3642450
- Visual Captions: https://research.google/blog/visual-captions-using-large-language-models-to-augment-video-conferences-with-dynamic-visuals/ ;
  https://research.google/pubs/pub52074/ (DOI 10.1145/3544548.3581566) ;
  https://github.com/google/archat (`content/interactive_image.ts`)
- Inner Thoughts: https://arxiv.org/abs/2501.00383
- ChatMuse: https://arxiv.org/abs/2607.18556

Meeting copilots:

- Cluely: https://docs.cluely.com/feature/liveinsights ; https://en.wikipedia.org/wiki/Cluely
- Natively: https://github.com/Natively-AI-assistant/natively-cluely-ai-assistant
  (`electron/intelligence/autoAnswer/SimpleAutoAnswer.ts`,
  `electron/context-intelligence/policies/mode-policy-registry.ts`,
  `electron/services/dynamic-actions/`)

Broadcast and livestream fact-checking:

- Full Fact: https://fullfact.org/blog/2025/apr/multitasking-ai-tools-and-22785-words-of-preparation-how-we-live-fact-check/ ;
  https://fullfact.org/blog/2025/feb/how-ai-can-help-fact-checkers/ ;
  https://fullfact.org/ai/
- Squash: https://reporterslab.org/the-lessons-of-squash-our-groundbreaking-automated-fact-checking-platform/ ;
  https://www.poynter.org/fact-checking/2020/how-the-duke-reporters-lab-used-the-political-conventions-to-perfect-its-automated-fact-checking-program/
- LiveFC: https://arxiv.org/abs/2408.07448 ; https://doi.org/10.1145/3701551.3704128
- Factiverse: https://www.factiverse.ai/blog/our-takeaways-from-the-worlds-first-real-time-fact-checking-service
- Footnote: https://github.com/jordanpeele/footnote (`HOW_FOOTNOTE_DECIDES.md`,
  `CHANGELOG.md`, `pacer.js`, `docs/CALIBRATION_REPORT_5_2026-08-14.md`)
- Other open-source demos, not analysed in depth:
  https://github.com/alandaitch/live-fact-checker (TRUE/FALSE/UNCERTAIN) ;
  https://github.com/santoshkkashyap25/live-rag-fact-checker

Datasets and proactive-agent research:

- Datasets: MAD https://arxiv.org/abs/2508.12186 ;
  MAD2 https://arxiv.org/abs/2606.11420 ;
  TRILOGUE https://arxiv.org/abs/2609.04452 ;
  podcasts https://arxiv.org/abs/2502.01402 ;
  TREC ToT 2025 https://arxiv.org/abs/2601.20671
- Proactive agents: https://arxiv.org/abs/2410.12361 ;
  https://arxiv.org/abs/2602.01532 ;
  https://arxiv.org/abs/2510.13105 ;
  https://arxiv.org/abs/2509.09255
