# Session lifecycle and what Carl keeps

Type: grilling
Status: resolved
Blocked by: 05

## Question

How does a session start and end (who starts it, what ends it: a tap, silence, a time limit), and what, if anything, does Carl keep once it ends: nothing at all, a recap of the fact cards shown, transcripts? If anything is kept, who may see it, and what are the others at the table entitled to (seeing it, having it deleted)?

## Context from resolved tickets

- From [Social contract at the table](05-social-contract.md): the owner discloses Carl at the start and anyone's objection means it doesn't run; anyone can pause, and nothing is heard or kept while paused.
- From [Situations Carl serves](03-situations.md): sessions run 30 min to 2 h in the background on the owner's phone.
- From [Fact card behaviour](06-fact-card-behaviour.md): the screen keeps a card history for the session (earlier fact cards, newest first), and a live transcript line can be switched on. Decide what happens to both when the session ends.
- From [Success criteria](07-success-criteria.md): a dev version runs *recording sessions* (visibly marked, separately disclosed; anyone's objection means no recording). The test corpus keeps their audio and the owner-corrected Markdown; raw logs are deleted once corrected. Decide who may see recordings and what the others at the table are entitled to (hearing them, having them deleted).

## Answer

Settled with the owner in a grilling session.

- **Start.** The owner taps **Start** on Carl's page after telling the table. Nothing is heard before that tap. The listening indicator appears when the session starts.
- **End.** Anyone at the table can **End** the session with one tap, just as anyone can pause. A session also ends on its own after **30 min without an utterance**, whether paused or not, and when the page is closed. There is no hard time limit. The monthly cost cap still stops Carl.
- **What a normal session keeps: its fact cards only.**
  - When the session ends, its card history moves into the **card archive**, reached through a menu. The archive holds earlier sessions' fact cards (title, fact, source, time), grouped by session.
  - The archive is kept on the owner's phone until the owner deletes it. There is no automatic expiry.
  - The transcript and the live transcript line are discarded when the session ends. No audio is kept.
  - The archive can be opened **only when no session is running**, so one table never sees another table's cards.
  - The archive is the owner's. Anyone who was at the table may ask to see a session's cards, or to have them deleted, and the owner honours it.
- **What development mode keeps.** Development mode runs **recording sessions**. Each recording session keeps its fact cards, the full transcript, the audio and the full log of every model call.
  - This changes [Success criteria](07-success-criteria.md): the raw logs are no longer deleted once the Markdown is corrected. They are kept along with everything else.
  - Each recording session is **deleted automatically 6 months** after it was recorded.
  - Recordings are heard or read only by the owner and by the models Carl is tested with. They never go into the repo.
  - Anyone recorded may ask to hear or read the recording, or to have it deleted. Deletion removes the **whole session**, because cutting one voice out of the audio isn't practical. The owner honours a request without asking why.
- **Model providers: no limit, stated openly.**
  - The spec puts no limit on what the providers of each stage keep or train on.
  - Carl's documentation names each stage's provider and links to its retention terms.
  - The spec gives the owner a suggested disclosure line saying the conversation goes to cloud AI services, so the table's consent is informed.

Glossary updated in `CONTEXT.md`: *Session*, *Card archive*, *Recording session*.

## Comments

- Extended by [Check the previous Carl's lessons against our plan](08-check-previous-carl-lessons.md): a normal session also adds to a **failure log** (no conversation content, 30-day expiry), and the suggested disclosure line also says that the location goes to cloud AI services.
- Superseded in part by [Resolve the spec's open issues](10-spec-open-issues.md): the cost cap no longer stops Carl (a **monthly budget** only warns); a recording session's corrected Markdown outlives its 6-month deletion; the card archive also keeps listening time and the owner's marks and notes, which the table may see or delete.
