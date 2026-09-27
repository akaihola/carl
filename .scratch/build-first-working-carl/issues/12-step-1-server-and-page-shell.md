# Step 1: Server and page shell

Type: task
Status: open
Blocked by:

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). The
[First working Carl spec](../../first-working-carl/spec.md) is the source of
truth.

## What to build

- **The Python server** ([Architecture](../../first-working-carl/spec.md#2-architecture)):
  - an asyncio server with a WebSocket library, managed with `uv`, serving
    both the page and the WebSocket;
  - a `carl` command with `serve`, listening on `PORT` (8080 by default) as
    the container expects;
  - a cheap health endpoint with no side effects, `GET /api/health`, for the
    loading page's poll. It sits under `/api/`, so it never reaches the
    Worker ([Hosting](../../first-working-carl/spec.md#hosting)).
- **The page shell** ([The page](../../first-working-carl/spec.md#the-page)):
  - plain HTML, CSS and JS modules, with no build step and no framework;
  - Atkinson Hyperlegible self-hosted, with its licence;
  - the dark screen whatever the phone's theme
    ([Overall](../../first-working-carl/spec.md#overall));
  - no third-party calls.
  - The Start screen and everything else on it come with step 2. Until then
    the page shows only the connection's state.

## Done when

- [ ] `uv run carl serve` serves the page and `/api/health` locally.
- [ ] The page loads nothing from any other origin.
