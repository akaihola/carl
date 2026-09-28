# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- State is recorded as a `Status:` line near the top of each issue file
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## Build tickets

Rules for writing and working the build tickets, such as
`.scratch/build-first-working-carl/issues/`, from step 1's cloud session
([session retro](../../.scratch/session-retro/report.md)):

- **One session per ticket.** Size a ticket for one agent session, and split
  a bigger one into sub-tickets before starting it. The session ends with
  the `next-step` skill.
- **`Waiting on:`** near the top names what an open ticket waits for
  besides its blockers. `Waiting on: owner` means what's left needs the
  owner: a phone session, a decision, a correction. A condition, such as
  `Waiting on: a day of logs after 2026-09-27 19:47 UTC`, means it waits on
  that. Remove the line once it's met. The `next-step` skill never hands
  such a ticket to a session by itself.
- **A figure goes into the ticket as soon as it is measured, never
  before.** Give its date, how it was measured and the raw number. Never
  write an expected figure to correct later.
- **Name the condition to wait on, not a duration:** "once `python3
  deploy/logs.py --until-quiet` returns", not "wait 20 minutes".
- **Dry-run a long test on a compressed schedule first,** with minutes as
  seconds, so a flaw in the test shows in a minute rather than an hour. A
  connection being observed gets its own process, apart from any probes.
- **A ticket that deploys behind Cloudflare** checks that gated responses
  stay out of its cache (`Cache-Control: private`; see "Things to know" in
  [docs/operations.md](../operations.md)).

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When `to-tickets` writes tickets

Write them in the build tickets' form, not the skill's template, so the
`next-step` skill can find them:

- Carl has no triage labels. The top lines are plain `Type: task`,
  `Status: open` and `Blocked by: NN, NN`, never `ready-for-agent` or bold
  labels, since `next-step` only picks a ticket with `Status: open`.
- A ticket that adds to an existing effort, such as
  `build-first-working-carl`, goes in that effort's `issues/` and takes the
  next free number there instead of starting again at `01`.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
