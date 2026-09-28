# Step 9: Acceptance

Type: task
Status: open
Waiting on: owner
Blocked by: 09

Build step 9 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth.

## What to do

Run one 2-hour recording session at a real dinner, end to end on the phone.
This is the first version's definition of **done**
([What "done" means](../../first-working-carl/spec.md#what-done-means)):

- it runs end to end on the phone without breaking;
- it is recorded completely: every speech-to-text event and every model call,
  each with its config, response time and cost, with check time and cost
  measured. A gap caused by a dropped connection still counts as recorded
  completely.

Done has no quality targets. Precision, recall, check time and cost are
measured later, on the test corpus, in the separate comparison effort.

## Done when

- [ ] One 2-hour recording session at a real dinner ran end to end on the
      phone without breaking.
- [ ] Its event log is complete in the sense above.
- [ ] Its corpus file is generated.
- [ ] A short summary is written under an `## Answer` heading here: the
      listening time, the number of candidates and cards, the check times
      (median and 90th percentile), the cost per hour, any outages, and
      anything that broke or nearly broke.

What comes after is the [next version](../../first-working-carl/spec.md#15-next-version),
unordered, and the comparison effort. Neither is ticketed here.
