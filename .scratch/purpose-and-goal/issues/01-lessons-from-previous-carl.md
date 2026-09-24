# Lessons from the previous Carl

Type: research
Status: resolved
Blocked by:

## Question

What did the previous Carl implementation (git history before commit 36d60c3, "clear all files for a clean-slate ng implementation") try, and which of its behaviours and lessons still hold? Be critical: the model and vendor landscape has changed a lot since it was built, so separate lessons about the *purpose and user experience* (likely durable) from ones about specific models, APIs or workarounds (likely stale). Findings go in `docs/research/previous-carl-lessons.md`.

## Answer

Findings: [docs/research/previous-carl-lessons.md](../../../docs/research/previous-carl-lessons.md).

The previous Carl was a three-day prototype (Dec 2025). It began as a general "contributes when appropriate" voice assistant and ended as a silent checker of claims and open questions, built on Gemini Live, with no evaluation against recorded conversations. Nearly every fix made it show *less*.

- **Durable (purpose/UX):** silent by default; never show that a claim is correct; stick to the two triggers; give the table time to find the answer itself before showing a card; drop a verdict once the conversation has moved on; fact cards must stand alone and be readable across a table; filter out unverifiable, private, situational and opinion questions; the only real examples are Finnish, so expect Finnish.
- **Stale:** specific models, using one audio model for both transcription and deciding, the Q/A numbering protocol, the voice-activity-detection and silence workarounds, the CORRECT/SKIP text replies, streaming checker text straight to the screen.
- **Unacknowledged failures:** the intended filtering prompt was never actually used; there was no confidence gate, so hedges and error text reached the screen; no fact card showed a source; speakers were never identified.
