---
name: next-step
description: End this session's ticket and hand over to the next session, started automatically when all went smoothly or else as a prompt for the owner to paste. Use when the session's ticket is done, or when it can't go on without the owner. Never start a second ticket in the same session.
---

# Next step

Carl is built one ticket per session ([AGENTS.md](../../../AGENTS.md),
Sessions). Step 1's session ran eight steps in one context until
auto-compaction dropped the details, and then had to dig numbers back out of
its old transcript ([session retro](../../../.scratch/session-retro/report.md),
failure 9). A fresh session per ticket, with the ticket as the handover,
avoids that.

## 1. Close the ticket

- Follow the `verify-before-claiming` skill. Run the tests just now, commit
  and push everything to `main`, and check that the `tests` workflow's run
  for the pushed SHA succeeded (`mcp__github__actions_list`, method
  `list_workflow_runs`, resource `test.yml`). The run takes about a
  minute. If it failed, read its logs and fix it; that is still this
  ticket.
- The ticket says where it stands. Each box ticked has its evidence, and
  each figure has its date and how it was measured. The ticket gets
  `Status: resolved` when every box is ticked. Otherwise a comment says
  what's left, and a `Waiting on:` line says who or what it waits on
  ([issue tracker](../../../docs/agents/issue-tracker.md#build-tickets)).
- `git status` is clean.

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
  SHA, nothing is uncommitted, and no box was ticked without its evidence;
- nothing needs the owner: no question the spec doesn't answer, no change
  of plan or scope, no contradiction in the spec, no permission denied, no
  workaround the owner hasn't seen, no surprise in cost or in a deploy;
- step 2 found a next ticket;
- the chain is short enough. The prompt that started this session ends
  with `Chain: k of N` when a session started it, and then k must be
  less than N. A prompt without that line came from the owner, so k is 0
  and N is 3.

Otherwise stop for the owner, and put the reason in the first line of the
final message.

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

- **Handing over by yourself:** call `mcp__Claude_Code_Remote__create_session`
  with that prompt, `title` "Carl NN: <short title>" and `source_url`
  `https://github.com/akaihola/carl`. Leave out `environment_id` and
  `permission_mode`, so the new session inherits this one's. If the tool
  is missing or the call is refused, stop for the owner instead.
- **Stopping for the owner:** give the prompt for the ticket to do next.
  That is this one again if it isn't finished, and otherwise the next. Drop
  the `Chain:` line, since the owner's own prompt starts a new chain.
  If a session started this one (k ≥ 1), the owner may be away: send a
  one-line push notification if the tool is there.

## 5. Final message

Keep it short:

- the ticket and where it stands;
- the evidence: the tests, the CI run and any deploy;
- anything the owner needs to do;
- the new session's title, or the prompt to paste, in a code block.

Then stop. Do no more work in this session.
