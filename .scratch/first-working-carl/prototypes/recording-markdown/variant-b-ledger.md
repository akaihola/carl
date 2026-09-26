<!-- PROTOTYPE (throwaway) — variant B "ledger": a clean transcript with visible
     utterance ids, then one table of candidates; every owner mark lives in
     the table (and one "Missed" table), never in the transcript. -->
---
carl-corpus: 0
session: 2026-10-03-1912-7f3a
started: 2026-10-03T19:12:00+03:00
place: Helsinki, Kallio
listening: 1h46m
config: carl.toml@3be91c0
cost_usd: 0.81
status: not started   # not started | in progress | done
same_speaker: []      # e.g. [[A2, B1], [A1, B2]]
---

# Recording session 2026-10-03 19:12

## Candidates

Mark: `ok` (deserved / right to stay silent) or `wrong`, `nitpick`, `opinion`,
`contested`, `settled`, `not checkable`, `should show` (silent but deserved a
card), `bad match` (repeat matched the wrong candidate). Add a note if useful.

| Id | Utt | Kind | Outcome | Check | Card / restatement | Verdict | Mark | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | u014 | claim | plain | 6.8 s | Einstein ei reputtanut matematiikkaa. Hän hallitsi differentiaali- ja integraalilaskennan jo ennen 15 ikävuotta. ([Wikipedia](https://fi.wikipedia.org/wiki/Albert_Einstein)) | both wrong · same 0.93 · sup 0.96/0.91 · `plain:agreed` | | |
| C2 | u022 | question | plain | 9.4 s | Casablancan (1942) ohjasi Michael Curtiz. ([Britannica](https://www.britannica.com/topic/Casablanca-film-1942)) | both answered · same 0.97 · sup 0.94/0.95 · `plain:agreed` | | |
| C1′ | u030 | repeat | → C1 | – | "But he did fail maths" | same-as p 0.81 | | |
| C3 | u041 | claim | silent | – | "Kemijoki is the longest river in Finland." | A right · B wrong · `silent:contradiction` | | |
| C4 | u052 | claim | silent | – | "Tampere is the largest inland city in the Nordics." | both right · `silent:claim-right` | | |
| C5 | u060 | claim | hedged, late | 23.1 s | Todennäköisesti: Suomessa on noin 56 000 järveä. ([SYKE](https://www.syke.fi/)) | B only · sup 0.71 · `hedged:single-verified` | wrong | 56 000 = lakes ≥ 1 ha; 188 000 was right |

## Missed

| Utt | Kind | What Carl should have said |
| --- | --- | --- |
| u071 | claim | Sibelius completed seven symphonies; he destroyed the eighth. |

## Transcript

Edit the text after the label to fix what was said; keep `uNNN` and the time.

```
u001 00:00:04 A1  No niin, onks kaikilla juotavaa?
u002 00:00:07 A2  Joo.
u003 00:00:09 A3  Mä otan vielä vettä.
…
u014 00:04:31 A2  Einstein muuten reputti matikan koulussa, se on ihan tunnettu juttu.   [C1]
u015 00:04:36 A3  Oikeesti?
u016 00:04:39 A1  Mä luulin et se oli myytti.
…
u022 00:07:12 A3  Who directed Casablanca, by the way?   [C2]
u023 00:07:15 A1  Ei mitään hajua. Joku Curtis?
…
u030 00:11:40 A2  But he did fail maths, didn't he?   [C1′ → C1]
…
u041 00:18:02 A4  Suomen pisin joki on Kemijoki.   [C3]
---- paused 00:21:10–00:27:30 ----
u052 00:28:02 B1  Tampere on Pohjoismaiden suurin sisämaakaupunki.   [C4]
…
u060 00:33:15 B2  Suomessa on muuten about 188 000 järveä.   [C5]
…
u071 00:41:20 B1  Sibelius sävelsi kahdeksan sinfoniaa.
---- gap 01:02:10–01:02:50 ----
…
```
