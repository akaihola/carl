# Session retro: would a skill have prevented step 1's failures?

Session `8b4682e5-6388-4747-b0ae-e35f2027d68d` ran in a Claude Code cloud
container on 2026-09-27. It split ticket 02 into tickets 12–19, built 12–15
and CI (789350f, 87f5d5d), and then carried on through steps 2–8 in the same
context.

## What the evidence covers

The local transcript has 318 lines and starts at an auto-compaction
(15:24 UTC) that dropped about 772k tokens. Everything before that is
known only from the compaction summary at line 4. That period includes
the 12–15 build and the first deploys. The full pre-compaction transcript
was a separate JSONL inside the cloud container (the agent greps it at
L81) and is not on this machine.

So the patterns below that come from before the compaction rest on the
summary's one-line accounts, and their costs are rough. Commits 789350f
and 87f5d5d were not reverted or redone later; the failures cluster in
deployment and operations, not in the 12–15 code.

## Failures and matching skills

Line numbers (L) are lines of the raw JSONL. "Anthropic" means
[anthropics/skills][a-skills] or the official plugin marketplace
[anthropics/claude-plugins-official][a-plugins].

| # | Failure | Cost | Root cause | Helpful skill | Confidence | Alternative fix |
|---|---------|------|------------|---------------|------------|-----------------|
| 1 | The cold-start measurement kept failing because traffic kept the container warm. The agent waited on a timer instead of watching logs, and did so again after the compaction even though the summary recorded the lesson (L4, L225). | ≥2 owner turns and a throwaway container before the compaction; about 20 min and 6 turns after it | Skipped check | None. superpowers' [condition-based-waiting][sp-cbw] states the right principle ("wait for the actual condition, not a guess about how long it takes"), but it is written for flaky tests and would not trigger during an ops measurement. | — | Add a rule to `docs/operations.md`: judge idleness from the last line of the container logs, never from a clock. Commit the log-watching script; it is not in `deploy/`. |
| 2 | The cloud container's TLS proxy broke Docker builds, blocked the `scw` download and needed `WSS_PROXY`; Chromium was flaky through it (L4) | Unknown; probably many turns | Cloud environment; ticket 02 named the proxy but not the workarounds | None. No collection has a skill about this environment. | — | Already written up in `docs/operations.md` (lines 117–130). A SessionStart script or cloud environment setup script could apply them: export the CA bundle for `deploy.sh`, set `WSS_PROXY=$HTTPS_PROXY`, and copy `scw` out of the mirror image. |
| 3 | Parallel subagents for steps 2–8 shared one checkout. Their uncommitted files broke the test suite, and the Stop hook nagged about uncommitted changes (L4) | A few turns per incident | Wrong assumption: that several writers can share one worktree | superpowers [subagent-driven-development][sp-sdd] (third party) has the rule "Never dispatch multiple implementation subagents in parallel (conflicts)". [dispatching-parallel-agents][sp-dpa] says not to dispatch in parallel when "agents would interfere (editing same files, using same resources)". | Medium for the rule; low for installing either skill. Both bring a worktree-and-branch workflow that conflicts with the main-only rule in `AGENTS.md`. | An `AGENTS.md` rule: subagents that edit files run one at a time, or use the Agent tool's `isolation: "worktree"` and hand back a commit. |
| 4 | A commit went in after a failing pytest run, because piping through `tail` hid the exit status (L4) | Low; the failing commit was caught | Skipped check | superpowers [verification-before-completion][sp-vbc] (third party). Its gate "RUN … READ: Full output, check exit code, count failures", applied before "Committing", addresses exactly this. | High | A git pre-commit hook that runs `uv run pytest -q`, or `set -o pipefail` in the commit command |
| 5 | Cloudflare cached the gated `.js`/`.css` at the edge for 4 h and injected its beacon (L4). Fixed in c7adcb6. | About 20 min and a redeploy; gated files were exposed without the pass meanwhile | Missing knowledge: CDNs cache by file extension unless the response is `private` | None. I checked the official `security-guidance` hook prompts and the `claude-security` skill: neither covers CDN caching of authenticated responses. | — | Already fixed: `tests/test_server.py` asserts the header, and `docs/operations.md` explains it. For future steps, a "behind a CDN" checklist line in deploy tickets. |
| 6 | The 2-hour connection test's minute-70 probe closed the 57.5-minute connection it was meant to observe; fixed with `--hold-only` (2078a95) (L4) | About 1 h of extra test time and a code change | Wrong assumption: that probes on one client would not disturb the held connection | None | — | Dry-run long tests on a compressed schedule (minutes as seconds) first. The ticket could have said the hold connection gets its own process. |
| 7 | `scw` v1 container arguments were found by trial and error: memory size format, startup probe, `registry-image`, and a 409 on a double redeploy (L4) | Unknown; probably 5–10 failed calls | Missing knowledge | Weak: Matt Pocock's [research][mp-research] skill (third party, already in `.claude/skills/`) sends the agent to primary sources. It is built for writing a findings file, so it's heavy for looking up CLI flags. | Low | Read `scw … --help` before the first call. `deploy/deploy.sh` now holds the working commands. |
| 8 | The auto-mode classifier denied creating the container and running `wrangler deploy`. You had to interrupt and approve in a typed message, and a secrets file had to be sent again (L4) | 3–4 owner turns plus waiting time | Cloud environment | None. The built-in `fewer-permission-prompts` skill only adds read-only commands, and deploys aren't read-only. | — | Add `permissions.allow` entries in `.claude/settings.json` for `deploy/deploy.sh` and `wrangler deploy`, or list the pre-approved deploy actions in the task prompt |
| 9 | One context ran steps 1–8 until auto-compaction. Afterwards it grepped the old JSONL to recover numbers and commands (L81, L161). | About 5 turns; the detail lost to the summary is unknown | Wrong assumption: that one session could hold every step | Weak: Matt Pocock's [handoff][mp-handoff] (third party) writes a document for a fresh session. It is user-invoked only (`disable-model-invocation: true`), so it helps only if you run it. | Low | Start one session per step, and write every measurement into its ticket as soon as it is taken |
| 10 | Small slips (L4, L168): `pkill -f` killed the agent's own shell twice; the ticket's cold-start figure ("about 5 s") was committed before the 9.9 s measurement and then rewritten 4 times; a scripted replace failed its assert; a flaky timing bound was loosened | 1–2 turns each | Skipped check | [verification-before-completion][sp-vbc] covers the premature "about 5 s" claim ("evidence before claims"). [condition-based-waiting][sp-cbw] would cover the flaky bound only if the test wasn't measuring timing on purpose, and I can't tell that from the summary. | Medium for the premature claim; low for the rest | A one-line `AGENTS.md` note: stop processes by PID, not `pkill -f` |

### Skills that were available and unused

The cloud container had `domain-modeling`, `grilling`, `prototype`,
`research`, `setup-matt-pocock-skills` and `wayfinder` in
`.claude/skills/`, plus Claude Code's built-in skills. The part of the
transcript I can see has no Skill calls. The only installed skill that
touches any failure is `research`, for #7, and that match is weak. I can't
tell whether any skills were invoked before the compaction.

### What I searched

For each failure, I read the candidate SKILL.md before counting it as a
match. I searched:

- [anthropics/skills][a-skills]: all 20 skills.
- [anthropics/claude-plugins-official][a-plugins]: 31 skills, plus the `security-guidance`, `claude-security`, `hookify`, `session-report` and `claude-code-setup` plugins.
- [obra/superpowers][sp]: all 15 skills, at 2026-09-25 HEAD.
- [mattpocock/skills][mp]: all 38 skills, at 2026-09-18 HEAD.
- The [travisvn/awesome-claude-skills][aw1] and [hesreallyhim/awesome-claude-code][aw2] lists.
- A keyword grep of the locally cloned jeremylongshore/claude-code-plugins collection.

I found nothing else that addresses these root causes.

## Recommendations, ranked

1. **Adopt superpowers' [verification-before-completion][sp-vbc]** (it covers #4 and part of #10). Copy that one SKILL.md into `.claude/skills/` (it is MIT-licensed) rather than installing the whole plugin. The full plugin's bootstrap skill pushes worktrees, branches and brainstorming, which fight the main-only workflow. A pre-commit pytest hook is the stronger fix for #4 and works even when the skill isn't loaded.
2. **Add an `AGENTS.md` rule for subagents that write files** (#3): run them one at a time, or with `isolation: "worktree"`. This takes the one useful rule from subagent-driven-development without its workflow.
3. **Pre-approve deploy commands in `.claude/settings.json`** (#8).
4. **Add a SessionStart or environment setup script for the cloud container** (#2). It turns the workarounds in `docs/operations.md` into something that runs automatically.
5. **Change how tickets are written and how sessions are run** (#1, #6, #9, part of #10):
   - one session per build step;
   - record each measurement in the ticket as soon as it is taken, never before;
   - for operations checks, name the condition to wait on (for example, the last log line) instead of a duration;
   - dry-run long tests on a compressed schedule first.

Five of the ten failures (#1, #2, #5, #6, #8) have no matching skill anywhere
I looked. They came from the environment, from Cloudflare and Scaleway
specifics, or from test design, and the fixes above are rules, scripts and
settings rather than skills.

[a-skills]: https://github.com/anthropics/skills
[a-plugins]: https://github.com/anthropics/claude-plugins-official
[sp]: https://github.com/obra/superpowers
[sp-vbc]: https://github.com/obra/superpowers/blob/main/skills/verification-before-completion/SKILL.md
[sp-sdd]: https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md
[sp-dpa]: https://github.com/obra/superpowers/blob/main/skills/dispatching-parallel-agents/SKILL.md
[sp-cbw]: https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/condition-based-waiting.md
[mp]: https://github.com/mattpocock/skills
[mp-research]: https://github.com/mattpocock/skills/blob/main/skills/engineering/research/SKILL.md
[mp-handoff]: https://github.com/mattpocock/skills/blob/main/skills/productivity/handoff/SKILL.md
[aw1]: https://github.com/travisvn/awesome-claude-skills
[aw2]: https://github.com/hesreallyhim/awesome-claude-code

## Comments

- 2026-09-28: Adopted the ranked recommendations.
  1. Carl's own [`verify-before-claiming`](../../.claude/skills/verify-before-claiming/SKILL.md)
     skill. Copying superpowers' SKILL.md was refused by the cloud
     session's permission classifier as untrusted code, so the owner can
     copy it by hand if the original is wanted. Also
     [`.githooks/pre-commit`](../../.githooks/pre-commit), which runs
     pytest before a commit that changes code.
  2. [AGENTS.md](../../AGENTS.md)'s Sessions: subagents that edit files run
     one at a time or in worktrees; stop processes by PID.
  3. [`deploy/worker.sh`](../../deploy/worker.sh), so the Worker's deploy
     is one command an allow rule can match. The allow rules themselves go
     in `.claude/settings.json`, which the classifier refused to let the
     agent write (self-modification), so the owner adds them.
  4. [`deploy/cloud-setup.sh`](../../deploy/cloud-setup.sh), for the owner
     to paste into the environment's setup script, and the SessionStart
     hook [`.claude/hooks/session-start.sh`](../../.claude/hooks/session-start.sh),
     which the same `.claude/settings.json` registers.
  5. The [issue tracker's build-ticket rules](../../docs/agents/issue-tracker.md#build-tickets),
     `Waiting on:` lines on the tickets that wait on the owner, the
     [`next-step`](../../.claude/skills/next-step/SKILL.md) skill (one
     ticket per session, then the next session starts by itself or the
     owner gets a prompt to paste), and [`deploy/logs.py`](../../deploy/logs.py)
     with its rule in [docs/operations.md](../../docs/operations.md#logs):
     judge the container's idleness from its logs.
