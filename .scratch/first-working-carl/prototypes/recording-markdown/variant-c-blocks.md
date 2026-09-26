<!-- PROTOTYPE (throwaway) — variant C "blocks": readable transcript, and each
     candidate as a fenced YAML block right after its utterance. The generator
     fills every field except `mark`/`note`; a checker rejects a file with an
     empty `mark` on a shown card or an unknown value. -->

# Recording session 2026-10-03 19:12

```yaml carl-session
session: 2026-10-03-1912-7f3a
place: Helsinki, Kallio
listening: 1h46m
config: carl.toml@3be91c0
cost_usd: 0.81
status: not started      # not started | in progress | done
same_speaker: []         # e.g. [[A2, B1]]
```

**A1** · 00:00:04 · No niin, onks kaikilla juotavaa?
**A2** · 00:00:07 · Joo.
**A3** · 00:00:09 · Mä otan vielä vettä.
…
**A2** · 00:04:31 · Einstein muuten reputti matikan koulussa, se on ihan tunnettu juttu.

```yaml carl-candidate
id: C1
kind: claim
shown: plain
check_time_s: 6.8
card: "Einstein ei reputtanut matematiikkaa. Hän hallitsi differentiaali- ja integraalilaskennan jo ennen 15 ikävuotta."
source: https://fi.wikipedia.org/wiki/Albert_Einstein
restated: {A: "Einstein failed mathematics at school.", B: "Albert Einstein reputti matematiikan koulussa."}
verdict: {A: wrong, B: wrong, same_fact: 0.93, supported: [0.96, 0.91], verified: [download], reason: plain:agreed}
mark:                    # deserved | wrong | nitpick | opinion | contested | already settled | not checkable
note:
```

**A3** · 00:04:36 · Oikeesti?
**A1** · 00:04:39 · Mä luulin et se oli myytti.
…
**A3** · 00:07:12 · Who directed Casablanca, by the way?
**A1** · 00:07:15 · Ei mitään hajua. Joku Curtis?

```yaml carl-candidate
id: C2
kind: open question
shown: plain
check_time_s: 9.4
card: "Casablancan (1942) ohjasi Michael Curtiz."
source: https://www.britannica.com/topic/Casablanca-film-1942
verdict: {A: answered, B: answered, same_fact: 0.97, supported: [0.94, 0.95], verified: [download, snippet], reason: plain:agreed}
mark:
note:
```
…
**A2** · 00:11:40 · But he did fail maths, didn't he?

```yaml carl-candidate
repeat_of: C1
p: 0.81
mark:                    # ok | bad match
```
…
**A4** · 00:18:02 · Suomen pisin joki on Kemijoki.

```yaml carl-candidate
id: C3
kind: claim
shown: no
verdict: {A: right, B: wrong, reason: silent:contradiction}
mark:                    # ok | should show
```

*— paused 00:21:10–00:27:30 —*

**B1** · 00:28:02 · Tampere on Pohjoismaiden suurin sisämaakaupunki.

```yaml carl-candidate
id: C4
kind: claim
shown: no
verdict: {reason: silent:claim-right}
mark:
```
…
**B2** · 00:33:15 · Suomessa on muuten about 188 000 järveä.

```yaml carl-candidate
id: C5
kind: claim
shown: hedged
late: true
check_time_s: 23.1
card: "Todennäköisesti: Suomessa on noin 56 000 järveä."
source: https://www.syke.fi/
verdict: {A: not found, B: wrong, supported: [null, 0.71], verified: [snippet], reason: hedged:single-verified}
mark: wrong
note: 56 000 counts lakes ≥ 1 ha; 188 000 (≥ 5 a) is the usual figure and was right.
```
…
**B1** · 00:41:20 · Sibelius sävelsi kahdeksan sinfoniaa.

```yaml carl-missed
kind: claim
should_say: Sibelius completed seven symphonies; he destroyed the eighth.
```

*— gap 01:02:10–01:02:50 —*
…
