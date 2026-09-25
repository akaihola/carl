# Fact card behaviour

Type: prototype
Status: resolved
Blocked by: 04, 05

## Question

How does a fact card look and behave: what the screen shows while Carl is listening but has nothing to say (prior art: near-silence reads as broken), what it contains, when it appears relative to the utterance, how many may appear and how often, how it fades or is dismissed, and how claims differ from answered open questions on screen?

## Context from resolved tickets

- From [Situations Carl serves](03-situations.md): the card is shown on a phone propped up for the whole table, so it must be readable from 0.5–2 m on a phone-sized screen, and written in the conversation's main language (Finnish or English).
- From [Edges of the purpose](04-edges-of-purpose.md): cards come in two confidence bands, plain and hedged ("probably", "maybe"). The prototype should show how a hedged card reads next to a plain one, for both a claim and an answered open question. Every card carries a source. A card whose candidate the table has already resolved is dropped, so decide what happens to a card that is on screen when that happens.
- From [Social contract at the table](05-social-contract.md): the screen always shows a listening indicator (and a distinct paused state), plus a one-tap pause anyone can reach; this is also the natural answer to "what shows while Carl has nothing to say". Card wording states the claim's gist and the fact, never the speaker, in a neutral reference-book voice.


## Assets

- Prototype (throwaway): [prototypes/fact-card-prototype.html](../prototypes/fact-card-prototype.html), also published as a private artifact: https://claude.ai/artifact/Vd9hpnzxb7mv1BNRTadkPb. Three screens (A Spotlight, B Ledger, C Ambient) played against one scripted Finnish dinner conversation, with knobs for check time (3/8/20 s) and what happens when the table settles a card already on screen.

## Answer

Settled with the owner by reacting to the prototype.

- **Screen: Spotlight (A) for the current card, Ledger (B) for history.** One large card at a time, readable across the table. Earlier cards from the session collect in a **card history** in the Ledger style: newest on top, older ones smaller and dimmer.
- **A card stays until someone taps it away.** No timer while nothing is waiting.
- **Cards queue.** When another card is waiting, the one on screen gives way either on a timer or when someone taps it, and the next card is shown. Cards never stack on screen.
- **The table settles a card already on screen → mark it.** The card stays, marked "Settled at the table" / "Ratkesi pöydässä". A candidate the table settles before its card is ready is still dropped (from *Edges of the purpose*).
- **Claims and answered open questions look different: a coloured label** (Claim / Väite, Question / Kysymys, in different colours). Hedged fact cards are also marked visually, not only by "probably"/"maybe" in the wording.
- **Live transcript line: welcome, but can be switched on and off.** It shows the latest utterance Carl heard next to the listening indicator. When on, it doubles as proof that Carl is listening.
- **Check time (end of utterance to card): not decided here.** It moves to *Success criteria*, which already covers latency tolerances. In the prototype, a 3 s check showed the Great Wall card before the table corrected it; with 8 s the card never appeared.
- Unchanged from earlier tickets: the listening indicator and one-tap Pause are always visible, and between cards they are the only things on screen.

Glossary updated in `CONTEXT.md`: *Card history*, *Live transcript line*.
