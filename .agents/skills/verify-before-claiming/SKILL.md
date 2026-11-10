---
name: verify-before-claiming
description: Check with a fresh command before saying something is done, fixed, passing, deployed or measured. Use before every commit and push, before ticking a ticket's box or writing a figure into a ticket, before resolving a ticket, before trusting a subagent's report, and before ending a build step.
---

# Verify before claiming

A claim about Carl's state is made only right after a command has shown it
in this session. Step 1's cloud session committed after a failing pytest
run, because `| tail` hid the exit status, and wrote a cold-start figure
into its ticket before measuring it
([session retro](../../../.scratch/session-retro/report.md), failures 4 and
10). The idea comes from obra/superpowers' `verification-before-completion`
skill; this is Carl's own version.

## The gate

Before you claim anything:

1. Name the command whose output would prove it (the table below).
2. Run it now, in full. A run from before your last edit doesn't count.
3. Read its exit status and the whole of its output: the failure count,
   the warnings, the skipped tests.
4. If it confirms the claim, make the claim and name the evidence ("906
   passed, exit 0"). If it doesn't, say what it did show.

Never read a test run through a pipe that hides its status. `uv run pytest
-q | tail -3` exits with `tail`'s status. Run it without the pipe, or check
`${PIPESTATUS[0]}`, or start the command with `set -o pipefail;`.

## What counts as evidence

| Claim | Evidence | Not evidence |
| --- | --- | --- |
| The tests pass | `uv run pytest -q` just now: exit 0 and its "N passed" line | An earlier run, one test file, a piped run |
| CI is green | The GitHub Actions run for the pushed commit's own SHA succeeded | The local run |
| It's deployed | `scw container container get` shows the new image tag and `ready`, and the logs show the server starting with that commit | `deploy/deploy.sh` exiting 0 |
| A figure (cold start, latency, cost, battery) | The run just taken, and how it was taken | The figure you expected; one run given as typical |
| A ticket's box is ticked | Exactly the evidence the box names | "It should work" |
| A subagent finished its part | Its diff, read by you, and a test run by you | Its report |
| A flaky test is fixed | Its cause understood, and the test run many times over | One green run after loosening a bound |

## Writing it down

- Write a figure into its ticket as soon as it's measured, with the date
  and how it was measured. Never write an expected figure into a ticket
  before measuring it.
- Tick a box only when its evidence is in hand. When some of it waits on
  the owner (a phone at a real table), leave the box open and say what's
  left in the ticket's comments.

## Warning signs

Stop and run the check when you notice yourself writing "should", "probably",
"seems to" or "looks fine" about something checkable, feeling done before
running anything, about to commit, push or deploy on an old run, or
loosening a test's bound to get green.
