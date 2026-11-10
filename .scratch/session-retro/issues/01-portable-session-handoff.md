# Make Carl's session handoff usable across agents

Type: task
Status: resolved
Owner: the coding agent in the session-learning thread
Blocked by:

Antti receives incomplete instructions when a Carl session leaves work for
him, and Codex and Pi cannot currently discover Carl's own workflow skills.
Keep one shared copy of the handoff and verification skills, make the
handoff describe complete owner actions, and preserve the owner's current
decision about test data.

## Done when

- Claude Code, Codex and Pi have a supported discovery path to the same
  handoff skill and its verification dependency.
- The handoff works without Claude-specific GitHub or session tools and
  gives the owner the account, computer, directory, complete command,
  success condition and destination for the result.
- Antti has an explanation of pipeline exit statuses and what deleting
  the terminal capture would remove; the capture is retained unless he
  requests deletion.
- The provider-terms ticket records Antti's 2026-11-10 decision that
  training restrictions are unnecessary for the current nonsensitive
  tests with team members.

## Comments

- 2026-11-10: Claimed for the [session-learning conversation]. The agent
  will edit the skills, check discovery and links, and report the result
  in that conversation. No application or deployment changes are needed.

## Answer

Antti now gets a handoff that identifies who acts next and includes
complete commands, prerequisites, success conditions and where to return
the result. Claude Code, Codex and Pi share one maintained copy of the
[handoff skill] and its [verification dependency]. The handoff can check
GitHub CI through available tools or `gh`, and falls back to a copyable
prompt when an authorized fresh-session tool is unavailable.

The [provider-terms ticket] records Antti's 2026-11-10 decision: preventing
training is unnecessary for current tests with team members because he
ensures their conversations contain no sensitive information. No account
settings were inspected or changed.

### Pipeline explanation

Bash normally reports the exit status of the last command in a pipeline.
Thus `git merge ... | tail -3 && git push ...` can run the push after a
failed merge: `tail` successfully printed output and returned zero. Prefer
running consequential commands without output-filtering pipes. When a
pipe is needed, `set -o pipefail` makes an earlier command's failure count
as pipeline failure; the caller still needs to check that status or use
`&&` before a dependent action. It does not stop later commands by itself.
The [existing pipe rule] has not been widened by this change; Antti asked
for its explanation.

### What deletion would remove

The retained terminal capture is 60,645 bytes and 1,066 lines. It contains
the former assistant's exact progress and final replies, selected shell
commands, partial output and intermediate diffs, including failed edits
and the merge pipeline above. Many tool calls are collapsed as
`ctrl+o to expand`; this is not the complete structured session log.

Deleting it would remove that local evidence of the sequence and wording.
The committed code, issue answers, measurements, decisions and [original
retrospective] remain in Git. The retrospective was based on a separate
JSONL transcript (one structured record per line); no copy of that
transcript was verified during this task. The terminal capture is
untracked, so Git cannot restore it after deletion. Keep it for now:
Antti asked what would be lost, and has not requested deletion.

### Verification on 2026-11-10

- Codex's local app-server `skills/list` discovered `next-step` and
  `verify-before-claiming` in this repository's shared skill directory.
- The installed Pi 1.4.0 skill loader read both skills with no diagnostics
  for either skill. Its installed package discovery code and documentation
  support the shared directory.
- Claude Code's directory symlinks resolve to the shared files. Every
  relative Markdown file link in both skill entry points exists through
  either path. Claude's documented symlink discovery was checked; an
  interactive Claude Code skill invocation was not run.
- The skill-creator frontmatter validator accepted both skills.
- `uv run pytest`: 912 passed in 32.70 seconds, exit 0.
- The terminal capture's SHA-256 is
  `0ed5fb0cc1da8a2b9f67d070bbba0ba3a6e5dac0f22213fc747b08ccb1871998`.

[session-learning conversation]: t3-thread://v1/9cb5a228-0c7f-491d-a84a-53cb2ecc7060
[handoff skill]: ../../../.agents/skills/next-step/SKILL.md
[verification dependency]: ../../../.agents/skills/verify-before-claiming/SKILL.md
[provider-terms ticket]: ../../build-first-working-carl/issues/11-read-openai-and-perplexity-terms.md#comments
[existing pipe rule]: ../../../.agents/skills/verify-before-claiming/SKILL.md#the-gate
[original retrospective]: ../report.md
