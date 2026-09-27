# Step 1: pytest in GitHub Actions

Type: task
Status: resolved
Blocked by: 12

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). The
[First working Carl spec](../../first-working-carl/spec.md#ground-rules) is
the source of truth.

## What to build

- A GitHub Actions workflow that runs pytest with `uv` on every push to
  `main`, from the locked dependencies.
- No live provider calls in CI. The tests refuse any connection that isn't
  to the local machine, so a test that would call a provider fails instead.

## Done when

- [x] The workflow runs on a push to `main` and passes.

## Answer

Built on 2026-09-27: `.github/workflows/test.yml` runs `uv sync --locked`
and `uv run pytest` on every push to `main` (and by hand), on Python 3.13
from `.python-version`. Its first run, on commit 87f5d5d, passed in 19 s:
[run 36317290923](https://github.com/akaihola/carl/actions/runs/36317290923).

`tests/conftest.py` refuses every connection that isn't to the local
machine, and `tests/test_no_network.py` checks that it does, for a plain
socket and for aiohttp.
