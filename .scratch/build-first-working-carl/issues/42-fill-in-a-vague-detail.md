# Fill in a detail the speaker left vague

Type: grilling
Status: open
Waiting on: owner

Not part of the first working version. The owner raised it while marking
session `20260928T081440Z-bf362b` of the test corpus.

At 00:15:45 A1 said: "Mikäs se oli se joku aika sitten joku firma kehitti
tämän kuulolaitteen…" ("What was it, some company developed this hearing aid
a while ago…"). The hearing aid follows the wearer's gaze and mutes everyone
except the person they look at. Nobody named the company, and the table
moved on. The decision model flagged it as a claim (C15). Both fact-finders
found it right, so it stayed silent (`silent:claim-right`).

The owner would like Carl to fill in such a detail, here the company or the
device, even when nobody asks for it.

## To settle

- Does this already fit the open-question trigger? "Mikäs se oli…" is the
  speaker wondering, much like the spec's own example "what was that actor's
  name…" ([product spec](../../purpose-and-goal/spec.md)). If it does, the
  miss is the decision model's, and a fix to `prompts/decision.md` is
  enough.
- If it doesn't, this is a new trigger. It goes against the product spec's
  non-goals ("no definitions, pertinent numbers, 'did you know' asides") and
  against "Nothing else: no asides" in `AGENTS.md`, so both would change.
  Where does filling in a vague detail ("some company", "that one film")
  end and an aside begin?
- Precision: several research groups have built gaze-steered hearing aids.
  When more than one answer fits, should Carl show nothing, or hedge?
- How many more cards would it bring? Each card interrupts the table.

## Comments
