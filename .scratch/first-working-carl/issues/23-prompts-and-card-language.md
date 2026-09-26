# Prompts, card language and the source blocklist

Type: grilling
Status: resolved
Blocked by: 

## Question

Where do the decision, settle, fact-finding and fact-checking prompts live so
there is one source of truth (a previous-Carl lesson), and how are they
versioned with each recording session alongside the config file?

- How is the card's language chosen when the talk mixes Finnish and English:
  the candidate utterance's language, the session's majority, or a setting?
- Which model writes the card in that language, and does the fact-checking
  model judge the card in the same language as its excerpt?
- Where does the source blocklist live, and how do the fact-finders' prompts
  ask for primary or reference sources?

## Answer

Settled with the owner in a grilling session (2026-09-26). The spec already
fixes cards in "the conversation's main language"; the blocklist was already
placed in the per-deploy config by
[Splitting verdict confidence](10-confidence-bands.md) and
[Hosting and secrets](13-hosting-and-secrets.md); and the fact-finders already
write the draft cards ([Provisional models](07-provisional-models.md)).

**Prompts: one source of truth**

1. **One file per prompt** in the repo: `prompts/decision.md`, `settle.md`,
   `fact-finding.md`, `fact-checking.md` and `same-fact.md` (the agreement
   call). Each has `{placeholders}` the server fills. Prompts belong to the
   pipeline, not to an adapter, so both fact-finders get the same text.
2. Prompts are **written in English** and name the language to write in.
3. No prompt text anywhere else: not in code, not in the config file. The
   prompt files are committed and baked into the image with the config.
   Startup fails if a template leaves a placeholder unfilled.

**Versioning with recording sessions**

4. A prompt's **version is a short content hash** of its file.
5. At session start the recording stores a copy of the config file and of
   every prompt file, next to the build's git commit.
6. Each model call's event records the prompt's name and hash and the
   filled-in values, not the rendered text. A replay rebuilds the exact
   prompt from these.

**Card language**

7. The **card language** (new term in `CONTEXT.md`) is the majority language
   by word count over the last 10 minutes of final utterances, from Soniox's
   per-token language tags. Carl works it out itself; no model decides it.
8. With fewer than ~50 words in that window, or on a tie, the candidate
   utterance's language is used instead.
9. There is no setting. Window length and word minimum are in config. Each
   candidate's events record the chosen language and the word counts behind
   it.
10. Example: a Finnish dinner, someone quotes a wrong claim from an English
    song lyric: the card is in Finnish.

**Who writes the card, and from which sources**

11. Carl passes the card language to both fact-finders, and each writes its
    draft card's title and one-sentence fact in it directly.
12. The search language is **not steered**: the fact-finders search wherever
    the best source is. The source excerpt stays verbatim in the source's own
    language, since verification matches it word for word.
13. Carl itself adds the claim/question label (Väite / Claim, Kysymys /
    Question) and the hedge prefix ("Todennäköisesti:" / "Probably:") in the
    card language. No model writes them.

**Fact-checking across languages**

14. The fact-checking model and the same-fact call judge the card and excerpt
    **as they are**, even in different languages; their prompts say so. No
    translation step: it would add latency, cost and another model that
    could get things wrong.
15. Each verdict event records the card's and the excerpt's languages, so the
    comparison map can see whether cross-language pairs do worse.

**Source blocklist and source preference**

16. The blocklist is a list of **domain suffixes** in the config file
    (`reddit.com` also blocks `old.reddit.com`). The initial list covers the
    categories [Splitting verdict confidence](10-confidence-bands.md) names:
    forums and Q&A sites, social media, video platforms, user-edited wikis
    other than Wikipedia.
17. Carl checks the draft card's source URL against it after the
    fact-finders return. The list is never put in a prompt.
18. The fact-finding prompt adds one line: prefer primary sources (official
    bodies, statistics offices, the original publication) or reference works
    (encyclopedias including Wikipedia, dictionaries, major news outlets);
    never cite forums, social media or video. The blocklist is the backstop.

**Testing prompts**

19. A few hand-written example cases per prompt, each in Finnish and in
    English, under `prompts/examples/`, and a script that runs them against
    the configured models and prints the typed answers next to the expected
    ones.
20. It is run by hand after a prompt change, not in CI (it costs money and
    needs the network), and its results aren't stored. Real test-corpus cases
    replace these examples in the comparison map.

**Card language** is now in `CONTEXT.md`. No ADR: every choice here is a
prompt, config or small code change away from reversal.
