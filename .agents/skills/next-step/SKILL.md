---
name: next-step
description: End a Carl ticket session with evidence and complete owner actions, then prepare a fresh-session handoff. Use when the ticket is done or cannot continue without the owner, in Claude Code, Codex or Pi. Never start a second ticket in the same session.
---

# Next step

Carl is built one ticket per session ([AGENTS.md](../../../AGENTS.md),
Sessions). Step 1's session ran eight steps in one context until
auto-compaction dropped the details, and then had to dig numbers back out of
its old transcript ([session retro](../../../.scratch/session-retro/report.md),
failure 9). A fresh session per ticket, with the ticket as the handover,
avoids that.

## Agent compatibility

Keep this skill and its [verification dependency](../verify-before-claiming/SKILL.md)
in `.agents/skills/`, with relative directory symlinks in `.claude/skills/`.
Discovery paths checked on 2026-11-10: [Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)
and [Pi](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)
read `.agents/skills/`; [Claude Code](https://code.claude.com/docs/en/skills#choose-where-skills-load)
supports symlinked project skill directories. Use the tools available in
the current harness; GitHub and session tools are optional integrations.

## 1. Close the ticket

- Follow the [verify-before-claiming skill](../verify-before-claiming/SKILL.md).
  Run the tests just now, commit and push the ticket's changes to `main`,
  and check that the `tests` workflow's run
  for the pushed SHA succeeded. Use available GitHub tools, or
  `gh run list --workflow test.yml --commit <full-pushed-SHA>` followed by
  `gh run view <run-id>` to inspect its conclusion. If it failed, read its
  logs and fix it; that is still this ticket. If access is unavailable,
  record what remains unverified and give the owner complete check steps.
- The ticket says where it stands. Each box ticked has its evidence, and
  each figure has its date and how it was measured. The ticket gets
  `Status: resolved` when every box is ticked. Otherwise a comment says
  what's left, and a `Waiting on:` line says who or what it waits on
  ([issue tracker](../../../docs/agents/issue-tracker.md#build-tickets)).
- `git status` shows no uncommitted changes belonging to this ticket.
  Identify unrelated owner files; do not stage or delete them to make the
  checkout clean.

## 2. Find the next ticket

It is the ticket in `.scratch/build-first-working-carl/issues/` (or the
build effort the owner is on) with the lowest number that meets all of:

- it has `Status: open`;
- every ticket in its `Blocked by:` line is resolved;
- it has no `Waiting on:` line.

If none qualifies, there is no next ticket for an agent.

## 3. Decide whether to hand over by yourself

Start the next session yourself only if all of these hold:

- the ticket closed cleanly: the tests pass and CI is green on the pushed
  SHA, no ticket changes are uncommitted, and no box lacks its evidence;
- nothing needs the owner: no question the spec doesn't answer, no change
  of plan or scope, no contradiction in the spec, no permission denied, no
  workaround the owner hasn't seen, no surprise in cost or in a deploy;
- step 2 found a next ticket;
- the current instructions authorize starting a separate session and an
  available tool supports it; this skill does not grant that permission;
- the chain is short enough. The prompt that started this session ends
  with `Chain: k of N` when a session started it, and then k must be
  less than N. A prompt without that line came from the owner, so k is 0
  and N is 3.

Otherwise prepare the handoff prompt and stop. State who acts next and
why in the first line of the final message. Follow the current thread's
acceptance and settlement rules before starting any further work.

## 4. Hand over

The ticket is the handover. Anything the next session needs to know
belongs in a ticket; the prompt only points to it:

```
Carl, ticket NN: <title>
.scratch/build-first-working-carl/issues/NN-<slug>.md

Work only on this ticket, as AGENTS.md says, and end with the next-step skill.
main is at <short SHA>, CI green.
Chain: <k+1> of <N>
```

- **Handing over by yourself:** use the available, authorized fresh-session
  tool for this harness and bind it to this repository's `main` checkout.
  For Claude Code Remote, `mcp__Claude_Code_Remote__create_session` accepts
  the prompt, `title` "Carl NN: <short title>" and `source_url`
  `https://github.com/akaihola/carl`; omit `environment_id` and
  `permission_mode` to inherit them. Codex and Pi do not require that tool:
  if no suitable session tool is available, give the owner the prompt.
  If a call is refused, stop and report the reason.
- **Stopping for the owner:** give the prompt for the ticket to do next.
  That is this one again if it isn't finished, and otherwise the next. Drop
  the `Chain:` line, since the owner's own prompt starts a new chain.

## 5. Final message

Keep the opening useful on its own: name who acts next, the completed
deliverable, what changed for the owner, and whether the thread can be
settled. Keep supporting logs and long commands in `<details>` sections.
Include:

- the ticket and where it stands;
- the evidence: the tests, the CI run and any deploy;
- for each owner action: the account and computer, working directory,
  prerequisites (including which secrets file to load, never its contents),
  complete commands or UI steps, what success looks like, exactly what to
  return and to which thread or ticket, and who continues afterward;
- if acceptance is required: link the deliverable, say what to check and
  what acceptance records, and give the exact acceptance reply and where
  to send it. Do not request acceptance while authorized work is unfinished;
- the new session's title and link if one was actually started, or the
  prompt to paste when a further ticket is appropriate. Do not invent a
  next ticket for a self-contained request.

A recorded task or proposed handoff does not arrange execution. Distinguish
active work, an actual automatic trigger, owner action and acceptance.
When an answer belongs in this thread, say it stays open and whether
snoozing delays the actual continuation; do not promise an early wake
without evidence. Retain these handoff details in cloud sessions too,
where the owner's home-directory style guide may be unavailable.

Then stop. Do no more work in this session.
