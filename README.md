# OS Synchronization Assignment - Readers-Writers & Dining Philosophers (Python)


Four small Python programs. Each solves a classic synchronization problem with real threads, records every state change while it runs, and writes that log into a self-contained `simulation.html` that can be opened in any browser to replay the run.

## Contents

- [The four implementations](#the-four-implementations)
- [Requirements](#requirements)
- [Repository layout](#repository-layout)
- [Running](#running)
- [How the HTML is produced](#how-the-html-is-produced)
- [HTML controls and checks](#html-controls-and-checks)
- [Design in short](#design-in-short)
- [Deadlock, starvation and fairness](#deadlock-starvation-and-fairness)
- [Race conditions and mutual exclusion](#race-conditions-and-mutual-exclusion)
- [Results](#results)
- [Sample output](#sample-output)
- [Timeouts](#timeouts)
- [Known limitations](#known-limitations)
- [AI use and references](#ai-use-and-references)

## The four implementations

| # | Problem | Synchronization | Source file | Replay file |
|---|---------|-----------------|-------------|-------------|
| Q1 | Readers-Writers | Semaphores: `mutex`, `resource`, `turnstile` | `readers_writers/semaphore/readers_writers.py` | `generated_html/readers_writers_semaphore.html` |
| Q2 | Readers-Writers | Monitor: one `Lock` and one `Condition`, writers first | `readers_writers/monitor/readers_writers_monitor.py` | `generated_html/readers_writers_monitor.html` |
| Q3 | Dining Philosophers (4) | Semaphores: one per fork, plus `room = 3` | `dining_philosophers/semaphore/dining_philosophers_semaphore.py` | `generated_html/dining_philosophers_semaphore.html` |
| Q4 | Dining Philosophers (4) | Monitor: state array, one `Condition` per philosopher | `dining_philosophers/monitor/dining_philosophers_monitor.py` | `generated_html/dining_philosophers_monitor.html` |

Each program is one self-contained file (event recorder, checks and HTML template included), so each question can be run and marked on its own.

## Requirements

- Python 3, tested with CPython 3.12.3 on Linux. Other versions were not tested.
- Standard library only: `threading`, `time`, `random`, `json`, `os`, `sys`, `webbrowser`. No installation step.
- Any modern browser to view the HTML. The files work offline.
- No build step.

## Repository layout

```
OS_Task2/
|-- README.md
|-- run.sh                     runs all four programs (Linux, macOS)
|-- run.ps1                    runs all four programs (Windows PowerShell)
|-- readers_writers/
|   |-- semaphore/readers_writers.py
|   |-- monitor/readers_writers_monitor.py
|-- dining_philosophers/
|   |-- semaphore/dining_philosophers_semaphore.py
|   |-- monitor/dining_philosophers_monitor.py
|-- generated_html/            replay files copied here by the run scripts
|-- screenshots/               screenshots of the four replays
|-- ai_prompts/                AI prompt log
|-- references/                references
|-- report/                    written report
```

## Running

From the repository root:

```
python readers_writers/semaphore/readers_writers.py --no-browser
python readers_writers/monitor/readers_writers_monitor.py --no-browser
python dining_philosophers/semaphore/dining_philosophers_semaphore.py --no-browser
python dining_philosophers/monitor/dining_philosophers_monitor.py --no-browser
```

Without `--no-browser`, each program opens its replay in the default browser after writing it.

To run all four in order, use `./run.sh` (Linux, macOS) or `.\run.ps1` (Windows PowerShell). Both scripts run the four programs and then copy each `simulation.html` into `generated_html/`.

Each program:

- prints the event log as it happens;
- prints a block of checks at the end;
- writes `simulation.html` next to its own source file;
- opens that file in the default browser, unless `--no-browser` is given.

The constants at the top of each file (`NUM_READERS`, `NUM_WRITERS`, `ROUNDS`, `MEALS`, the delay ranges) can be changed before a run. Each run overwrites `simulation.html`, so copy the file to `generated_html/` under its own name if you want to keep it.

## How the HTML is produced

While the threads run, every state change (waiting, reading, writing, hungry, eating, fork picked up, and so on) is appended to a list. Each entry has a timestamp in milliseconds since the program started, and a snapshot of the synchronization state at that moment: the reader count, who holds the resource, who holds each fork, how many writers are waiting.

- In the monitor programs (Q2, Q4), the snapshot is read while the monitor lock is held, in the same locked step as the change, so the log cannot fall between two states.
- In the semaphore programs (Q1, Q3), the program does not read the semaphore objects. It keeps bookkeeping variables and updates them at each acquire and release, so the replay shows the state the program models.

After all threads have joined, the list is written as JSON into an HTML template. The page's JavaScript does not compute synchronization state itself. It displays the snapshots recorded in the event list, and derives only display lists (such as who is hungry) from them.

## HTML controls and checks

Each replay has:

| Control or panel | Meaning |
|------------------|---------|
| Play / Pause | Plays the recorded events at the chosen speed; the button changes between Play and Pause |
| Step | Applies one event |
| Reset | Returns to the start of the run |
| Speed (0.5x, 1x, 2x, 4x) | Changes the playback speed |
| Clock and event counter | Current timestamp and event number out of the total |
| Process cards | State of each reader and writer (Q1, Q2) or philosopher (Q3, Q4) |
| Resource or fork panel | Who holds the shared resource, or each of the four forks |
| Monitor or table panel | Monitor counters (Q2), or who is eating, hungry, and how many are in the room (Q3, Q4) |
| Timeline | One row per process, plus a row for the resource or each fork |
| Event log | Every recorded event; the current one is highlighted |
| Check list | The program's checks, shown in the page (Q2, Q3, Q4). Q1 shows its verdict in the header only |

The checks are run by the program, not by the page. They test rules such as no reader and writer inside together, no two writers at once, no lost update, no fork held twice, no neighbours eating together, and everyone finishing their meals or rounds. Checks marked "(info)" report a value and always pass.

## Design in short

- **Q1 semaphores.** `mutex` (1) guards `reader_count`. `resource` (1) is taken by the first reader and released by the last one, or held by a single writer. `turnstile` (1) is held by a waiting writer, so readers that arrive later queue behind it. The moment a reader finishes and the moment the reader group releases `resource` are logged as two separate events.
- **Q2 monitor.** One lock and one condition variable. The monitor keeps `active_readers`, `writer_active` and `waiting_writers`. A reader waits while a writer is active or queued. A writer waits while anyone is inside. Every wait is in a `while` loop. Every state change that could unblock a waiting thread calls `notify_all()`.
- **Q3 semaphores.** `fork[i]` is a binary semaphore for each fork, and `room` is a counting semaphore with value 3. At most three philosophers can compete for forks at once, so the four-way circular wait cannot form.
- **Q4 monitor.** `state[i]` is THINKING, HUNGRY or EATING. `_test(i)` grants both forks in one step when philosopher `i` is hungry and neither neighbour is eating. Nobody holds one fork while waiting for the other. Q4 has no separate "acquiring forks" state, because both forks are granted at once; HUNGRY covers the whole wait. Q3, by contrast, has an ACQUIRING state.

## Deadlock, starvation and fairness

Python's `Semaphore` and `Condition` do not guarantee first-in, first-out wake-up, and the programs do not add queues to provide it. So the claims are limited to what the code establishes:

- **Q1.** A waiting writer closes the turnstile, so readers that arrive later must queue behind it. Readers that passed the turnstile before the writer closed it can still enter first. Writers are not starved in practice in the recorded runs, but this is not proven.
- **Q2.** A writer that is queued cannot be overtaken by new readers. Readers can be starved if writers keep arriving. Writers are not first-in, first-out among themselves, so one writer could in principle be overtaken by another.
- **Q3.** The room limit prevents deadlock. Order among waiting philosophers is not guaranteed, so starvation is not excluded.
- **Q4.** Deadlock-free by construction. A hungry philosopher waits only while a neighbour is eating, and each `put_down` re-tests both neighbours. A philosopher could still wait a long time if its two neighbours keep taking turns.

No program claims absolute starvation freedom. Each run counts meals per philosopher and prints the counts, so starvation in that run can be seen.

## Race conditions and mutual exclusion

A race condition occurs when two threads access shared data concurrently and the result depends on their interleaving. In these programs the shared data is the resource (`shared_data` in Q1 and Q2) and the fork ownership table (Q3 and Q4). The writers' update is deliberately split into a read, a delay and a write. Without mutual exclusion, two writers could read the same old value and both write `old + 1`, losing one update. The final-value check (`final value equals number of writes`, and the no-lost-update check in Q2) detects exactly that outcome.

Mutual exclusion is the guarantee that only one thread is inside a critical section at a time. In Q1 and Q2 it is provided by the semaphores or the monitor lock around the resource; in Q3 and Q4 it is provided by the fork semaphores or the monitor's atomic grant. The checks confirm the guarantee in each run; they do not prove it for all possible interleavings.

## Results

Event counts and the figures below come from the replay files committed with this revision (the event data embedded in each `simulation.html`), and from four fresh runs of the same code. Concurrency results change from run to run, because the interleaving changes. The event counts are fixed by the program design, except for Q1, which depends on how many times the reader group releases the resource.

**Q1 Readers-Writers (semaphore).** Committed replay: 96 events, all rules held, maximum 4 readers reading at once, 12 "released resource" events, final value 6 (expected 6). Four fresh runs: 96 events each, maxima of 3, 3, 3 and 4 readers, all rules held every time.

**Q2 Readers-Writers (monitor).** Committed replay: 84 events, all 8 checks pass, maximum 5 readers at once, 15 reader requests (5 readers, 3 rounds each), final value 6 (expected 6). Two counts of "held back" readers are reported:

- *narrow*: a reader arrived while a writer was queued (`waiting_writers > 0`);
- *broad*: a reader arrived while a writer was active or queued.

| Run | Held back, narrow | Held back, broad |
|-----|------|------|
| Committed replay | 9 | 13 |
| Fresh run 1 | 3 | 5 |
| Fresh run 2 | 9 | 10 |
| Fresh run 3 | 8 | 10 |
| Fresh run 4 | 3 | 10 |

The broad count can never be smaller than the narrow count for the same run, because it includes it.

**Q3 Dining Philosophers (semaphore).** Committed replay: 112 events, all 7 checks pass, never more than 3 philosophers in the room, every philosopher ate 3 times, and in this run no two philosophers ate at the same moment (max eating at once = 1). Four fresh runs: 112 events each, all checks pass, and the maximum eating at once was 2, 1, 2 and 2. Two non-neighbouring philosophers eating together is allowed by the design and occurred in three of the four fresh runs.

**Q4 Dining Philosophers (monitor).** Committed replay: 52 events, all 6 checks pass, every philosopher ate 3 times, and two non-neighbouring philosophers ate at the same time (max eating at once = 2). Four fresh runs: 52 events each, all checks pass, and the maximum eating at once was 2 in each of the four runs.

<img width="1562" height="976" alt="Screenshot 2026-10-12 203248" src="https://github.com/user-attachments/assets/f0bca5e0-1c50-4138-b2bf-1cc6e84b07d9" />
<img width="1497" height="963" alt="Screenshot 2026-10-12 203320" src="https://github.com/user-attachments/assets/4da46b13-f73d-48ab-9f9a-4fa3c92855cf" />
<img width="1445" height="933" alt="Screenshot 2026-10-12 203356" src="https://github.com/user-attachments/assets/4f092880-57bf-40fa-a211-8c314123f823" />
<img width="1500" height="1013" alt="Screenshot 2026-10-12 202815" src="https://github.com/user-attachments/assets/7b150f70-b55c-4008-9be8-1abc9aa704f0" />


## Sample output

Excerpt from a fresh run of Q4 (`dining_philosophers_monitor.py --no-browser`), with the start and the final checks:

```
=== Dining Philosophers (MONITOR): philosophers=4 meals each=3 ===

[     0 ms] P0 THINKING  F0:- F1:- F2:- F3:-  sits down and starts thinking
[     1 ms] P1 THINKING  F0:- F1:- F2:- F3:-  sits down and starts thinking
[     1 ms] P2 THINKING  F0:- F1:- F2:- F3:-  sits down and starts thinking
[     1 ms] P3 THINKING  F0:- F1:- F2:- F3:-  sits down and starts thinking
...
  P3 ate 3 time(s)  (no starvation)

---- checks ----
PASS  1. no deadlock: every philosopher thread finished  5.66 s, limit 60.0 s
PASS  2. no starvation in this run: everyone ate MEALS times  meals P0=3, P1=3, P2=3, P3=3
PASS  3. a fork was never granted while still held
PASS  4. neighbours never ate at the same time / nobody ate without both forks
PASS  5. (info) max philosophers eating at the same time  max eating at once = 2 (2 = two non-neighbours overlapped)
PASS  6. monitor back in a consistent final state (all thinking, all forks free)
RESULT: all checks passed - no deadlock occurred
```

## Timeouts

| Program | Thread join | If a deadlock occurs |
|---------|-------------|----------------------|
| Q1 Readers-Writers (semaphore) | `join()` with no timeout | The program does not finish; it waits forever |
| Q2 Readers-Writers (monitor) | 60 s limit (`JOIN_TIMEOUT`) | Check 7 fails and the result is reported |
| Q3 Dining Philosophers (semaphore) | 60 s limit (`JOIN_TIMEOUT`) | The no-deadlock check fails and the result is reported |
| Q4 Dining Philosophers (monitor) | 60 s limit (`JOIN_TIMEOUT`) | The no-deadlock check fails and the result is reported |

Q1 is written to wait for every thread, so a deadlock there would stop the program instead of being reported.

## Known limitations

- Thread scheduling is not deterministic, so event order, the maximum concurrency and the held-back counts differ between runs.
- Concurrency figures (readers overlapping, philosophers eating together) depend on timing. They are reported as information, not as pass or fail. The one exception is Q2 check 1, which is also informational in this revision.
- The programs use `time.sleep` and random delays to make interleavings visible. Python runs one thread at a time in the interpreter, so the programs show logical interleaving, not parallel speed-up.
- In Q4 the RELEASING state is logged inside the monitor and is instantaneous, so it is only a sliver on the timeline.
- Timestamps are whole milliseconds, so several events can share one timestamp.
- The number of philosophers is fixed at four, as the assignment requires. The room size and fork numbering are written for four.
- The repository contains no automated unit tests. Verification is the program's own checks, plus comparison with the replay data.
- Windows was not tested for `run.ps1`.

## AI use and references

AI assistance was used for this assignment: GitHub Copilot Chat, using a Claude model, in VS Code. The full prompt log is in [`ai_prompts/prompts.md`](ai_prompts/prompts.md), and the references are in [`references/references.md`](references/references.md).
