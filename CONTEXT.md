# Carl

Carl is a live conversation fact-checker for private, personal use. It listens to
a conversation at a table and shows a short fact card when something said is
false or when a question goes unanswered.

## Language

### The conversation

**Utterance**:
One final (not interim) transcript segment attributed to a single speaker.
_Avoid_: Sentence, segment, chunk

**Candidate**:
An utterance the decision model flags as worth fact-checking; either a claim or an open question.
_Avoid_: Detection, hit, trigger

**Claim**:
A candidate stating something that can be checked as true or false against a public source. Opinions, predictions, private facts and contested questions are not claims.
_Avoid_: Statement, assertion

**Open question**:
A candidate where the conversation wonders about something and the table leaves it unresolved ("what was that actor's name…"). A disagreement the table can't settle ("1953 or '54?") is an open question too.
_Avoid_: Memory lapse, unanswered question

### The pipeline

**Decision model**:
The cheap, fast stage that runs on every utterance and decides whether it is a candidate.
_Avoid_: Detection, detector, classifier

**Fact-checking model**:
The stronger, slower stage that runs only on candidates and returns a verdict.
_Avoid_: Verifier, verification

**Verdict**:
The fact-checking model's result for a candidate: outcome, answer, source and confidence.

**Message-writing model**:
The stage that turns a confident verdict into a fact card.

**Fact card**:
The short message shown on screen: a title, a one-sentence fact and a source.
_Avoid_: Correction, banner, contribution

**Hedged fact card**:
A fact card whose wording ("probably", "maybe") carries a verdict that is likely but not confident. Below that band, no card is shown.
_Avoid_: Uncertain card, low-confidence card
