# Hosting and secrets

Type: grilling
Status: claimed
Blocked by: 05, 06, 16

## Question

Where is the first working version hosted (the page, and any server), how are provider API keys kept out of the page and the repo, who can reach it (only the owner's phone? a login?), and how are the normal and dev versions deployed?

## Comments

- Owner's steers from [What "done" means for the first working version](01-done-for-first-version.md#answer): see its answer.
- From [Where the card archive, failure log and recording sessions are kept](11-storage-expiry-deletion.md#answer): the host needs EU-only object storage with prefix lifecycle rules (180 days on `recordings/`, none on `corpus/`), no versioning, and a small store for the failure log with 30-day expiry. The owner reaches the bucket from their computer with an owner-only script.

- From [Metering running cost against the monthly budget](12-cost-metering.md#answer): the server store that holds the failure log also keeps per-session cost summaries and a month-to-date total indefinitely (no conversation content), and the per-deploy config file carries a price table and a fixed USD→€ rate.
