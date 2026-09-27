# Prompts

One file per prompt, named after the call that uses it (First working Carl
spec, [Prompts: one source of truth](../.scratch/first-working-carl/spec.md#prompts-one-source-of-truth)):
`decision.md`, `settle.md`, `fact-finding.md`, `fact-checking.md` and
`same-fact.md`. No prompt text exists anywhere else, in code or in the
config file.

- A `{placeholder}` is a lower-case name in braces, filled in by the server.
  The server refuses to start if a template has a placeholder that nothing
  fills, or if a stage's prompt file is missing. What fills each prompt is
  listed in `FILLS` in `src/carl/prompts.py`.
- A prompt's version is the first 8 hex digits of its file's SHA-256. Model
  calls record the prompt's name and version with the values filled in.
- The prompts arrive with the build steps that use them. The step-0
  smoke-test prompts in
  [`../.scratch/build-first-working-carl/smoke-test/prompts/`](../.scratch/build-first-working-carl/smoke-test/prompts/)
  are their first drafts.
- This README isn't a prompt.
