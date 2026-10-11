# AI tools used

Tool: GitHub Copilot Chat in VS Code (Claude model), used in a long back-and-forth while
building and testing the four programs. The agent also ran the programs and a headless
browser to check the generated pages.

## What I asked for (condensed)

1. Readers-Writers with semaphores in Python that records real events and generates an
   HTML replay; then a monitor version with `threading.Condition` and writer preference.
2. Several correction rounds on the semaphore version: open the HTML automatically, make
   the replay match the real critical-section boundaries, and separate "this reader
   finished" from "the resource was actually released". This took three attempts - the
   first two just moved the logging line around; the fix that stuck was to log the
   release together with `resource.release()` under one lock and to store who holds the
   semaphore in every event.
3. Fix the timeline cursor (the first version used a CSS `calc()` that multiplied two
   percentages, which is not valid CSS). Replaced by pixel arithmetic in JavaScript.
4. A final audit of the monitor version, with the instruction not to change anything
   unless a real problem was found. Nothing had to change.
   Implement both Dining Philosophers programs directly in Python:
5. Dining Philosophers using Semaphores: Use 4 philosophers, 4 chopsticks, and a room semaphore with room = N - 1 to prevent deadlock.
   Dining Philosophers using Monitors: Use Python's threading.Condition and a Dijkstra-style monitor to control philosopher states and chopstick access.
   Write both implementations from scratch in Python., Use  Python's standard library and keep both implementations consistent with the style and structure of my existing Python assignments.
6. Rewrite the file headers, documentation, and code comments in simple, natural, beginner-friendly English, as if I wrote them myself. Explain the             synchronization logic clearly without changing the correctness of the algorithms. Keep the comments useful for understanding the code and explaining it      during my Operating Systems viva.
   
## Manual changes / decisions that were mine

- Keep every question as exactly two files (program + generated HTML), no shared module.
- Report "did readers overlap" / "did two philosophers eat together" as information, not as
  a pass/fail check, because it depends on scheduling.
- State honestly that Python semaphores and conditions are not FIFO, instead of claiming
  starvation freedom.

## What I checked myself

Ran every program at least three times, read the console logs, stepped through the HTML
replays, and compared the event log against the panels. The agent's browser checks
(recomputing the state from the event order and comparing with what the page shows)
found two real display bugs in the philosophers pages (eating count during RELEASING,
and a deadlock banner that fired on a harmless transient), both fixed before submission.

## Reflection

The AI was fastest at boilerplate (HTML template, checks) and at spotting ordering bugs in
the logging. It was also wrong a few times in a confident way - twice it said the event
timing was fixed when it wasn't. The thing that actually helped was insisting on the
difference between "a process is done" and "the resource is free", and testing against
the recorded events rather than trusting the explanation.
