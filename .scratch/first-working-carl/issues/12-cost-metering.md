# Metering running cost against the monthly budget

Type: grilling
Status: open
Blocked by: 06, 07

## Question

How is running cost measured per session and per month across all four stages (provider usage fields, price tables, estimates), where is the running total kept, how does the owner set the monthly budget, and when does the over-budget warning appear?

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): the stages are now speech-to-text, decision, fact-finding (two in parallel, plus Perplexity per-search fees) and fact-checking (Jev bills input tokens only). Every call returns tokens, cost and latency.
- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): Soniox bills by stream duration, and the stream stays open with keepalives through the 2-minute reconnect grace period; it is closed during Pause.
