# Prior art in live conversation fact-checking

Type: research
Status: resolved
Blocked by:

## Question

What existing tools, products, demos and research systems do live fact-checking or question-answering on spoken conversation (not just broadcast/debate fact-checking pipelines), what exactly do they surface, when, and how do they avoid false corrections? Focus on scope and behaviour that could inform Carl's purpose; skip studies of how people feel about being corrected by a machine (Carl is an experiment, not a product). Findings go in `docs/research/prior-art-live-fact-checking.md`.

## Answer

Findings: [docs/research/prior-art-live-fact-checking.md](../../../docs/research/prior-art-live-fact-checking.md). Many web claims there are marked **[search]** because the proxy blocked direct page fetches; check them against the source before relying on them.

- **No shipped product does exactly what Carl does.** The closest are Even Realities G2 "Conversate" (smart glasses) and meeting copilots. None publishes its triggers, thresholds or accuracy.
- **The published precision strategies come from broadcast tools** (Full Fact, Squash, LiveFC, Footnote): a human in the loop, matching against claims already checked, two verifiers that must agree, "unverifiable" as the default verdict, never showing claims about named people or quotes, or claims that start with an unresolved pronoun.
- **A single model's self-reported confidence is not a usable threshold.** Wrong verdicts still scored 0.97–0.99. Only the lower of two independent verifiers separated right from wrong.
- **Short context has a known failure mode.** A pronoun cut off from what it refers to produced a false "False" card. Claims in dialogue are spread across turns, and checking casual speech for claims is much harder than checking debates.
- **Being too cautious has a cost too.** When an assistant barely ever appears, users read it as broken. The spec should say what Carl shows while it is listening but has nothing to say.
- **The open-question trigger has the least prior art.** Recalling something from a vague description ("tip of the tongue") is an unsolved problem.
