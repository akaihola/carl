# Decision model context and candidate de-duplication

Type: grilling
Status: resolved
Blocked by: 01, 07

## Question

How much context does the decision model get with each utterance (how many earlier utterances or seconds, speaker labels, date, time, location), which utterances skip it entirely (backchannel, very short turns), and how does Carl keep to one card per claim or open question per session: how is a candidate matched against earlier ones, and what does a repeat do?

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): the decision model gives typed answers only (a choice with probabilities), so matching a candidate against earlier ones cannot rely on it writing a restated claim.
- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): speaker labels are only meaningful within one speech-to-text stream; a new stream (Pause, drop, restart) brings fresh labels and a "(paused)" or "(gap)" marker in the decision context. Utterances are split at speaker changes (1–2-word false switches merged) and capped at about 30 s.

## Answer

Settled with the owner in a grilling session (2026-09-26).

**When the decision model runs**

1. **On every utterance**, and each call runs to the end: a newer utterance
   never cancels an unfinished call, so a claim followed at once by "Oh
   really?" still gets judged.
2. **Skipped:** only utterances made up entirely of words from a fixed
   Finnish/English backchannel and filler list (joo, niin, aha, mm, jaa, okei,
   yeah, right, uh-huh, wow…). No word-count cutoff, because short open
   questions ("Kuka se oli?", "'53 vai '54?") must reach the model. Skipped
   utterances still appear in later calls' context.

**What it sees**

3. **Context window:** the new utterance, marked as the one being judged, and
   up to the **10 preceding utterances from no more than the last 2 minutes**
   (config file). Only earlier speech, never later. Speaker labels, the
   "(paused)"/"(gap)" markers from ticket 08, date, time and location come
   with it; location's format is still in the map's fog. The fact-finding
   model gets the same window. The prompt tells the decision model to answer
   `none` when the claim's subject can't be resolved from the window.
4. **The session's earlier candidates** are listed in the input with Carl's
   own ids (C1, C2…), covering the whole session across Pauses and gaps, with
   no cap (a 2 h session has ~20–40, a few hundred tokens).

**One call recognises a repeat**

5. **Choices:** `none / claim / open question / same as C1 … Cn`. It is a
   single call with no extra latency, and the model can only name ids Carl
   gave it, so de-duplication stays in Carl's own state (previous-Carl
   lesson). Rejected: a second parallel call (double cost), text similarity
   (misses paraphrase and language switches), and matching draft cards after
   fact-finding (spends a search on every repeat).
6. **From probabilities to an outcome:**
   1. If the "same as" choices together reach **0.5**, it's a **repeat** of
      the most likely one.
   2. Otherwise, if `claim` + `open question` together reach the
      **candidate threshold** (starting at 0.5), it's a candidate of
      whichever is higher.
   3. Otherwise `none`.

   With no probabilities (a vendor without logprobs), the chosen answer is
   taken as is. Both thresholds live in the config file and are recorded
   with each recording session.
7. **How an earlier candidate is listed:** the fact-finding model gains an
   output field, the **candidate restated as one standalone sentence**
   ("Who played Rick in *Casablanca*?"), returned for every outcome, silent
   ones included. Until one arrives, the list shows the raw utterance. The
   first restatement to arrive from the two parallel fact-finders is used;
   the recording keeps both. The fact-checking model is **not** given the
   restatement: it judges "doesn't answer the candidate" against the original
   utterance and its context, so a fact-finder's misreading can't vouch for
   itself.

**What counts as the same, and what a repeat does**

8. **Same** = asserts the same thing or asks the same question, in any
   language or wording. Same topic isn't enough. "He did fail maths, though"
   repeats "Einstein failed maths". "He failed physics, actually" is a new
   claim. "It was '52, wasn't it?" after "1953 or '54?" is a new claim about
   the same question. So false corrections are still checked, as the spec
   requires.
9. **A repeat gets nothing new** if the earlier candidate got a card (it
   stays in the card history), ended silently (claim right, not found, below
   the hedge band, settled at the table) or is still in flight (no second
   check). A repeat of a candidate that **failed at a stage** (timeout,
   unavailable, bad output) is checked as a new candidate, since nothing was
   decided.
10. Each recorded repeat links to the candidate it matched, so the test
    corpus can mark wrong matches.

**Settling at the table** graduated into its own ticket,
[Tracking a candidate until its card](18-tracking-candidate-until-card.md).
It can reuse this list of earlier candidates, e.g. with a `settles Cn`
choice.

**Repeat** is now in `CONTEXT.md`. No ADR: every choice is a config or prompt
change away from reversal.
