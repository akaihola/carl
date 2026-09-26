# The can't-hear-or-check state and the failure log

Type: grilling
Status: claimed
Blocked by: 

## Question

Which signals from each stage flip the listening indicator to "can't hear or
check", when does it flip back, and what does the failure log record for
each (time, stage, error; no conversation content)?

Known signals so far: a dropped page–server connection, the 2-minute
reconnect grace period, a server restart, the speech-to-text connection
dropping while the server reopens it with backoff, the Scaleway handover at
~50 min, `overload` (more than 8 live candidates) and the 60 s candidate
timeout (from [Tracking a candidate until its card](18-tracking-candidate-until-card.md#answer)).
Open: does one failed candidate flip the indicator, or only a stage failing
repeatedly (how many, over what window)? Does a fact-finder down but the
other up count? How does the page show it, and which failures does the page
buffer itself?
