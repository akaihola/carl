# Step 1: Config file and prompt loader

Type: task
Status: open
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

- [ ] `carl serve` loads the config file and the prompts at startup, and
      fails on a bad config or an unfilled placeholder.
- [ ] pytest covers the config loading and the prompt loader's placeholder
      check and versions.
