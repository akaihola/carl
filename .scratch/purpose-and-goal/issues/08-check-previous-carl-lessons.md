# Check the previous Carl's lessons against our plan

Type: grilling
Status: resolved
Blocked by: 03, 04, 05, 06, 07, 09

## Question

Now that our own research and planning are done, which findings in [Lessons from the previous Carl](01-lessons-from-previous-carl.md) (`docs/research/previous-carl-lessons.md`) still apply, and which of them should change the plan before the spec is assembled?

## Answer

Settled with the owner in a grilling session, going through each finding in [Lessons from the previous Carl](01-lessons-from-previous-carl.md).

**Already in the plan, no change.** Silence by default and no confirmations of correct claims ([Edges of the purpose](04-edges-of-purpose.md)); only the two triggers, with no speech output and no chit-chat (Edges, `AGENTS.md`); dropping verdicts the conversation has overtaken (Edges, [Fact card behaviour](06-fact-card-behaviour.md), late cards in [Success criteria](07-success-criteria.md)); cards that stand alone and can be read across the table ([Social contract at the table](05-social-contract.md), Fact card behaviour); filtering out opinions, private facts and contested topics (Edges); a confidence gate and a source on every card (Edges); Finnish ([Situations Carl serves](03-situations.md)); measuring on recorded conversations (Success criteria); "just open a web page" (`AGENTS.md`). The old lesson "never show a hedge" stays overridden by *hedge, don't refuse*. The stale lessons (specific models, the Q/A protocol, keeping the Live API awake with silence, streaming prose to the screen, one check at a time) belong to the out-of-scope vendor and implementation efforts.

**What changes the plan:**

- **No grace period for open questions.** The previous Carl's early "wait for one more utterance" rule is not adopted. Open questions and claims are handled the same way: the card shows as soon as it is ready, and if the table gets there first, the existing rules apply (dropped before the card is ready, "Settled at the table" once it is on screen).
- **One card per claim or open question per session.** A repeated claim or question that already got a card gets nothing new. The earlier card is still in the card history.
- **Only fact cards and the listening indicator reach the screen.** A failed check is silent. When Carl can't hear or can't check at all (connection lost, a stage down, the monthly cost cap reached), the listening indicator shows that as its own state instead of claiming to listen.
- **Failure log.** A "Log" menu item opens a **failure log**: time, which stage failed (speech-to-text, decision, fact-checking, message writing, connection, cost cap) and the error message, with no conversation content. It can be opened during a session too. Entries older than 30 days are deleted automatically, and the owner can clear it at any time. This adds to [Session lifecycle and what Carl keeps](09-session-lifecycle.md), where a normal session kept only its fact cards.
- **Carl knows when and where.** Besides the transcript, Carl gets the date, time and the phone's precise location, taken at session start and updated while the session runs. The owner can switch location off, and Carl then gets only the date and time. The suggested disclosure line says that the location goes to cloud AI services along with the conversation. The card archive doesn't keep the location, but recording sessions keep it in their model-call logs.
- **Situational questions count once where and when are known.** A claim or open question qualifies if it can be checked against a public source *given where and when the table is* ("when was this church built?", "is the pharmacy on the corner open on Sundays?"). Private facts ("how old is my sister?") and opinions ("what should we order?") stay out. This narrows the "situational" exclusion in Edges of the purpose.
- **The screen stays on for the whole session.** The documentation tells the owner that a long session on a propped-up phone wants a charger.

Glossary updated in `CONTEXT.md`: *Claim* and *Open question* (checkable given where and when), *Listening indicator* (can't-hear state), new term *Failure log*.

## Comments

- Superseded in part by [Resolve the spec's open issues](10-spec-open-issues.md): "cost cap reached" is no longer a can't-hear-or-check state or a failure log stage. Going over the **monthly budget** only puts a warning on the listening indicator and the Start screen.
