# The corpus header says what was heard

Type: task
Status: open

Follows [ticket 09](09-step-8-corpus-and-costs.md) and
[ticket 38](38-test-material-sessions.md). The
[First working Carl spec](../../first-working-carl/spec.md#the-test-corpus-markdown)
is the source of truth, and this ticket changes it.

The test corpus will hold dinners and recorded talk played beside the phone
(podcasts, Parliament). A later comparison needs to tell them apart: a
broadcast has more speakers, a different register, and no table that
settles a point. A phone session with a speaker looks just like a dinner in
its corpus file. Only a `dev-send` run says what it was, in its start
event's `mic` (`{"source": "dev-send", "file": …}`), and the corpus file
doesn't show it.

## What to build

- **An owner field `material`** in the `yaml carl-session` header, after
  `same_speaker`: a short free text such as `dinner`, `Futucast #370 via
  speaker` or `dev-send: eduskunta-2026-05-21.wav`.
- **`generate`** prefills it from a `dev-send` start event
  (`dev-send: <file>`), and otherwise writes it empty, with a comment giving
  examples.
- **Kept like the other owner fields:** a corpus file whose `material` the
  owner has filled in counts as work, so `generate` keeps the file, as it
  does for marks, notes and `same_speaker` groups. A prefilled value that
  still matches the start event doesn't count.
- **`check`:** `material`, if present, is a string. It is optional, so
  files written before this ticket still pass, and the format stays 1.
- **The spec:** the header list in
  [The test corpus Markdown](../../first-working-carl/spec.md#the-test-corpus-markdown)
  gets the field.

## Done when

- [ ] pytest passes in GitHub Actions on push to `main`: `generate` with a
      `dev-send` start event and with a phone one, keeping a file whose
      `material` the owner filled in, and `check` on a file with and
      without the field.
- [ ] The spec's header list has the field.
- [ ] The corpus files from ticket 38's sessions have it filled in.
