# Step 4: Excerpts, blocklist, bands and card wording

Type: task
Status: open
Blocked by: 

Part of [step 4](05-step-4-first-cards.md). The
[First working Carl spec](../../first-working-carl/spec.md#6-fact-finding-fact-checking-and-confidence-bands) is the source of truth.

## What to build

Pure logic, plus A's page download:

- excerpt matching: B's excerpt as a substring of a snippet from the same
  URL; A's source downloaded (about 3 s) and searched, after normalising
  whitespace and quotation marks;
- the blocklist's domain-suffix matching;
- the bands with their reason codes: hedged for step 4, plain and the pair
  rules for step 5;
- the words Carl adds in the card language: the label, the hedged tag and the
  hedge prefix.

## Done when

- [ ] pytest covers each rule.
