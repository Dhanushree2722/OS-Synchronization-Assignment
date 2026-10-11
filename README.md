# OS Synchronization Assignment - Readers-Writers & Dining Philosophers (Python)

Student: Dhanushree (USN NNM24IS068)
Course: Operating Systems - process synchronization (AI-assisted assignment)

## What is in here

Four small Python programs. Each one solves a classic synchronization problem with real
threads, writes down every state change while it runs, and at the end turns that log into
a single `simulation.html` you can open in any browser to replay what actually happened.

| # | Problem | How it's synchronized | File | Replay |
|---|---------|-----------------------|------|--------|
| 1 | Readers-Writers | semaphores: `mutex`, `resource`, `turnstile` | `readers_writers/semaphore/readers_writers.py` | `generated_html/readers_writers_semaphore.html` |
| 2 | Readers-Writers | monitor: one `Lock` + `Condition`, writers first | `readers_writers/monitor/readers_writers_monitor.py` | `generated_html/readers_writers_monitor.html` |
| 3 | Dining Philosophers (4) | semaphores: one per fork + `room = 3` | `dining_philosophers/semaphore/dining_philosophers_semaphore.py` | `generated_html/dining_philosophers_semaphore.html` |
| 4 | Dining Philosophers (4) | monitor: Dijkstra's state array, one `Condition` per philosopher | `dining_philosophers/monitor/dining_philosophers_monitor.py` | `generated_html/dining_philosophers_monitor.html` |

There is no shared helper module on purpose - every program is one self-contained file
(event recorder, checks and HTML template included), so each question can be handed in on
its own.

## Requirements

- Python 3.10 or newer. Standard library only (`threading`, `time`, `random`, `json`,
  `os`, `sys`, `webbrowser`).
- Any browser for the HTML. Works offline.

## Running

From the repo root:

```
python readers_writers/semaphore/readers_writers.py
python readers_writers/monitor/readers_writers_monitor.py
python dining_philosophers/semaphore/dining_philosophers_semaphore.py
python dining_philosophers/monitor/dining_philosophers_monitor.py
```

or `.\run.ps1` (Windows) / `./run.sh` (Linux, macOS) to run all four one after another.

Each program prints the live event log, then a block of checks, then writes
`simulation.html` next to itself and asks the default browser to open it. Q2-Q4 take
`--no-browser` if you don't want that. All four join their threads with a 60 s limit, so a
deadlock would be reported as a failed check instead of hanging the program. The numbers at the top of each file
(`NUM_READERS`, `ROUNDS`, `MEALS`, delays ...) can be changed before a run.

## How the HTML is produced

Nothing in the page is scripted by hand. While the threads run, every state change
(waiting, reading, writing, hungry, eating, fork picked up ...) is appended to a list
together with a timestamp and a snapshot of the synchronization state at that instant
(reader count, who holds the resource, who holds which fork, how many writers are
waiting). The snapshot is taken at the exact point where the semaphore / monitor state
changes, under the same lock, so the log can't be "between" two states. After all threads
have joined, the list is dumped as JSON into an HTML template. The JavaScript in the page
then replays it: process cards, resource / fork status, a Gantt-style timeline, the full log,
and Play / Step / Reset / speed controls. Run the program again and the page changes,
because the interleaving changes.

The page also shows the result of the program's own checks (no reader/writer overlap,
no two writers at once, no lost update, no deadlock, everyone finished, ...).

## Design in short

- **Q1 semaphores.** `mutex(1)` guards `reader_count`. `resource(1)` is taken by the first
  reader and given back by the last one, or held by a single writer. `turnstile(1)` is
  held by a writer while it waits, so readers arriving later queue behind it. The moment
  a reader finishes and the moment the group actually releases `resource` are logged as
  two different events.
- **Q2 monitor.** One lock, one condition. `active_readers`, `writer_active`,
  `waiting_writers`. Readers wait while a writer is active *or waiting*; writers wait while
  anyone is inside. `wait()` always sits in a `while`, `notify_all()` on every change.
- **Q3 semaphores.** `fork[i] = Semaphore(1)`, `room = Semaphore(3)`. Only three of the
  four may reach for forks at once, so the circular wait can never close.
- **Q4 monitor.** `state[i]` in THINKING / HUNGRY / EATING, `test(i)` hands out both forks
  at once when neither neighbour eats, so no hold-and-wait.

## Fairness - what I can and can't claim

Python's `Semaphore` and `Condition` don't guarantee FIFO wake-up (the Java versions I
read used fair semaphores; Python has no such switch). So:

- Q1: a waiting writer blocks new readers, but a reader can in theory still race ahead
  on wake-up. Writer starvation is avoided in practice, not proven impossible.
- Q2: writers can't be starved; readers can, if writers keep coming.
- Q3: no deadlock is guaranteed by the N-1 room limit; order among waiting philosophers
  is not.
- Q4: deadlock-free, but a philosopher could wait indefinitely if both neighbours keep
  alternating. Every program counts and prints meals / operations per thread so this can be
  checked on each run.

## Results of the runs I kept

Defaults: 5 readers, 2 writers, 3 rounds; 4 philosophers, 3 meals. The numbers below are read
from the replay files committed in `generated_html/` (the same run as the screenshots), so they
can be checked against those files. Other runs give different numbers because the interleaving
changes - every program ran at least three more times with all checks passing.

- Q1 (`readers_writers_semaphore.html`): 96 events, final value 6 (= 2 writers x 3 rounds),
  max 5 readers reading at once, 12 "released resource" events, no overlap, all threads
  finished (4.1 s, limit 60 s).
- Q2 (`readers_writers_monitor.html`): 84 events, all 8 checks pass, max 5 readers at once.
  Of the 15 reader requests, 5 arrived while a writer was active or waiting and were held back
  (counted as reader "waiting" events whose snapshot has `writer_active` or `waiting_writers > 0`).
- Q3 (`dining_philosophers_semaphore.html`): 112 events, all 7 checks pass, never more than 3 in
  the room, everyone ate 3 times. In this particular run no two philosophers happened to eat at
  the same moment (max eating = 1); other runs showed 2.
- Q4 (`dining_philosophers_monitor.html`): 52 events, all 6 checks pass, everyone ate 3 times,
  two non-neighbours eating at the same time was observed (max eating = 2).

Screenshots of the four replays are in `screenshots/`, taken from these same files.

## Known limitations

- Scheduling is not deterministic, so event order differs between runs.
- "How many readers overlapped" / "did two philosophers eat together" depends on timing and
  is reported as information, not as pass/fail.
- In Q4 the RELEASING state happens inside the monitor and is instantaneous, so it is a
  sliver on the timeline.
- Timestamps are milliseconds since program start; several events can share one millisecond.

## AI use and references

See `ai_prompts/prompts.md` and `references/references.md`.
