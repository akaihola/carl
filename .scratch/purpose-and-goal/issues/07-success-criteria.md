# Success criteria

Type: grilling
Status: open
Blocked by: 04

## Question

What does "Carl works" mean for this experiment: a precision target (and any recall floor), how it is measured (e.g. a corpus of recorded table conversations with labelled candidates), and the tolerances for latency and running cost?

## Context from resolved tickets

- From [Edges of the purpose](04-edges-of-purpose.md): precision is judged against a threshold. Only errors that change the point, or that repeat a well-known myth, deserve a card, and hedged cards count as cards. Labelled data has to encode this: a nitpick card is a false positive, as is a card on an opinion, a contested topic, or a candidate the table already resolved.
- From [Fact card behaviour](06-fact-card-behaviour.md): the check time (end of utterance to card on screen) was left for this ticket. In the prototype, a 3 s check put a card up before the table corrected the claim itself, which then shows as "Settled at the table". With 8 s the table got there first and the card was dropped. The latency tolerance should weigh a card arriving too late against one arriving before the table has had its say.
