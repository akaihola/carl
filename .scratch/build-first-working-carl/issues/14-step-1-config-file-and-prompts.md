# Step 1: Config file and prompt loader

Type: task
Status: resolved
Blocked by: 12

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). The
[First working Carl spec](../../first-working-carl/spec.md) is the source of
truth: [Config file contents](../../first-working-carl/spec.md#13-config-file-contents)
and [Prompts: one source of truth](../../first-working-carl/spec.md#prompts-one-source-of-truth).

## What to build

- **The config file**, committed and baked into the image:
  - every setting and starting value in section 13;
  - each stage's provider, model and parameters as step 0 confirmed them
    ([ticket 01](01-step-0-provider-smoke-test.md#answer)), Soniox's
    included;
  - the price table: input, cached and output tokens per model, per search,
    and per audio hour;
  - the USD → € rate: the European Central Bank's reference rate on the day
    the file is first written;
  - the blocklist, starting from the smoke test's draft.
  - The values that stay out of it (section 13's second table) stay in code,
    the Worker or the bucket.
- **A strict loader:** startup fails on a missing setting, an unknown one or
  a wrong type, so a typo can't silently fall back to a default.
- **The `prompts/` folder and its loader:**
  - one file per prompt, with `{placeholders}` the server fills in;
  - a prompt's version is a short content hash of its file;
  - startup fails if a template has a placeholder that nothing fills, and
    if a stage's prompt file is missing.
  - The prompt texts arrive with the steps that use them. The smoke-test
    prompts in [`../smoke-test/prompts/`](../smoke-test/prompts/) are their
    first drafts.

## Done when

- [x] `carl serve` loads the config file and the prompts at startup, and
      fails on a bad config or an unfilled placeholder.
- [x] pytest covers the config loading and the prompt loader's placeholder
      check and versions.

## Answer

Built on 2026-09-27.

- `config.toml` holds every row of section 13's first table. The stages
  are those step 0 confirmed: Soniox `stt-rt-v5`; `gpt-6-luna` on OpenAI
  for the decision model and fact-finder A; `google/gemini-3.8-flash` on
  Perplexity for fact-finder B, with `search_type` web,
  `search_context_size` medium, `max_steps` 2 and reasoning `low`; and
  `typesafe/jev-1.13` on OpenRouter for fact-checking. `store: false` stays
  in the adapters' code, as a privacy choice.
- The price table is keyed by provider and model, and every stage must
  have an entry, so cost metering can't be skipped by accident.
- The USD → € rate is the ECB's reference rate as the ECB publishes it,
  1.1403 US dollars per euro. The file was first written on Sunday
  2026-09-27, so that is Friday 2026-09-25's rate.
- The backchannel list starts from the spec's words plus a few like them
  (juu, jep, mhm, hmm, jaha, öö, yep, oh, um, okay). It leaves out yes and
  no words, since those can answer or settle.
- `src/carl/config.py` loads it into frozen dataclasses. A missing or
  unknown setting, a wrong type (`true` isn't a number), a probability
  outside 0–1, a heartbeat not shorter than the silence, or a stage
  without a price stops startup. The config's version is a short hash, as
  a prompt's is.
- `src/carl/prompts.py` loads `prompts/*.md` (not `README.md`). A prompt's
  version is the first 8 hex digits of its SHA-256. `FILLS` lists what
  the pipeline fills into each prompt. Startup fails if a template has a
  placeholder not in its list, or if a listed prompt has no file. A
  placeholder is a lower-case name in braces, so JSON examples are left
  alone. `FILLS` is empty until step 3 brings the first prompt.
