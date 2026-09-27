# Step 1: pytest in GitHub Actions

Type: task
Status: open
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

- [ ] The workflow runs on a push to `main` and passes.
