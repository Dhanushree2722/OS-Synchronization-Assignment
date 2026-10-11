# OS Synchronization Assignment - Readers-Writers & Dining Philosophers (Python)

Student: Dhanushree (USN NNM24IS068)
Course: Operating Systems - process synchronization (AI-assisted assignment)
Repository: https://github.com/Dhanushree2722/OS_Task2

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
- [Results](#results)
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

- Python 3. The README asks for 3.10 or newer. The programs were run with CPython 3.12.3 on Linux; other versions were not tested.
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
python readers_writers/semaphore/readers_writers.py
python readers_writers/monitor/readers_writers_monitor.py --no-browser
python dining_philosophers/semaphore/dining_philosophers_semaphore.py --no-browser
python dining_philosophers/monitor/dining_philosophers_monitor.py --no-browser
```

To run all four in order, use `./run.sh` (Linux, macOS) or `.\run.ps1` (Windows PowerShell). Both scripts run the four programs and then copy each `simulation.html` into `generated_html/`. Neither script passes `--no-browser`, so a browser tab opens for each program. The PowerShell script was not executed in this repository's testing; the shell script was read but not run.

What each program does when it runs:

- prints the event log as it happens;
- prints a block of checks at the end;
- writes `simulation.html` next to its own source file;
- opens that file in the default browser, unless `--no-browser` is given.

The Readers-Writers semaphore program (Q1) does not accept `--no-browser` and always opens the browser. Q2, Q3 and Q4 accept the flag.

The constants at the top of each file (`NUM_READERS`, `NUM_WRITERS`, `ROUNDS`, `MEALS`, the delay ranges) can be changed before a run. Each run overwrites `simulation.html`, so copy the file to `generated_html/` under its own name if you want to keep it.

## How the HTML is produced

While the threads run, every state change (waiting, reading, writing, hungry, eating, fork picked up, and so on) is appended to a list. Each entry has a timestamp in milliseconds since the program started, and a snapshot of the synchronization state at that moment: the reader count, who holds the resource, who holds each fork, how many writers are waiting.

- In the monitor programs (Q2, Q4), the snapshot is read while the monitor lock is held, in the same locked step as the change, so the log cannot fall between two states.
- In the semaphore programs (Q1, Q3), the program does not read the semaphore objects. It keeps bookkeeping variables and updates them at each acquire and release, so the replay shows the state the program models.

After all threads have joined, the list is written as JSON into an HTML template. The page's JavaScript replays the list: process cards, resource or fork status, a Gantt-style timeline, the full event log, and playback controls. The page makes no independent calculation of the synchronization state.

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

The checks are run by the program, not by the page. They test rules such as no reader and writer inside together, no two writers at once, no lost update, no fork held twice, no neighbours eating together, and everyone finishing their meals or rounds. Checks marked "info" report a value and always pass.

## Design in short

- **Q1 semaphores.** `mutex` (1) guards `reader_count`. `resource` (1) is taken by the first reader and released by the last one, or held by a single writer. `turnstile` (1) is held by a waiting writer, so readers that arrive later queue behind it. The moment a reader finishes and the moment the reader group releases `resource` are logged as two separate events.
- **Q2 monitor.** One lock and one condition variable. The monitor keeps `active_readers`, `writer_active` and `waiting_writers`. A reader waits while a writer is active or queued. A writer waits while anyone is inside. Every wait is in a `while` loop, and every state change calls `notify_all()`.
- **Q3 semaphores.** `fork[i]` is a binary semaphore for each fork, and `room` is a counting semaphore with value 3. At most three philosophers can compete for forks at once, so the four-way circular wait cannot form.
- **Q4 monitor.** `state[i]` is THINKING, HUNGRY or EATING. `_test(i)` grants both forks in one step when philosopher `i` is hungry and neither neighbour is eating. Nobody holds one fork while waiting for the other.

## Deadlock, starvation and fairness

Python's `Semaphore` and `Condition` do not guarantee first-in, first-out wake-up, and the programs do not add queues to provide it. So the claims are limited to what the code establishes:

- **Q1.** A waiting writer closes the turnstile, so readers that arrive later must queue behind it. Readers that passed the turnstile before the writer closed it can still enter first. Writers are not starved in practice in the recorded runs, but this is not proven.
- **Q2.** A writer that is queued cannot be overtaken by new readers. Readers can be starved if writers keep arriving. Writers are not first-in, first-out among themselves, so one writer could in principle be overtaken by another.
- **Q3.** The room limit prevents deadlock. Order among waiting philosophers is not guaranteed, so starvation is not excluded.
- **Q4.** Deadlock-free by construction. A hungry philosopher waits only while a neighbour is eating, and each `put_down` re-tests both neighbours. A philosopher could still wait a long time if its two neighbours keep taking turns.

No program claims absolute starvation freedom. Each run counts meals per philosopher and prints the counts, so starvation in that run can be seen.

## Results

Concurrency results change from run to run, because the interleaving changes. Each number below states its source. Event counts and checks for the supplied replays come from the event data in the replay file. Audit runs A1 to A3 were three fresh runs of each program, made from the same source code.

**Q1 Readers-Writers (semaphore).** The replay committed in `generated_html/readers_writers_semaphore.html` (the run behind the screenshot) is recorded as: 96 events, final value 6 (expected 6), maximum **5** readers reading at once, 12 "released resource" events, all rules held. A separate copy of this replay that was checked directly for this README showed a maximum of 4 readers instead of 5, with the same event count and final value; this may be a different run of the same program rather than the same file, and is noted here for transparency. Three fresh runs of the program gave maxima of 4, 5 and 5 readers, which shows the number is not fixed from run to run.

**Q2 Readers-Writers (monitor).** The replay committed in `generated_html/readers_writers_monitor.html` is recorded as 84 events, all 8 checks pass, maximum 5 readers at once. There are 15 reader requests in total (5 readers, 3 rounds each). How many were "held back" depends on which requests are counted:

| Run | Held back for a queued writer only (`waiting_writers > 0` at arrival) | Held back because a writer was active or queued (broader count) |
|-----|------|------|
| Repository's committed replay | 9 | **5** |
| A second fresh run | 9 | 10 |
| A third fresh run | 3 | 8 |

The repository's README states **5**, which matches the broader count. The narrower count (only counting requests that arrived while a writer was specifically queued, not yet admitted) gives 9 for the same committed replay. Both are shown because the method was not stated in earlier drafts of this README; pick whichever definition your lecturer expects and keep it consistent with the number you quote.

**Q3 Dining Philosophers (semaphore).** Supplied replay: 112 events, all 7 checks pass, never more than 3 philosophers in the room, every philosopher ate 3 times. Audit runs: 112 events each, all checks pass, and at most one philosopher eating at a time in every run. In these runs, two philosophers never ate at the same moment.

**Q4 Dining Philosophers (monitor).** Supplied replay: 52 events, all 6 checks pass, every philosopher ate 3 times, and two non-neighbouring philosophers ate at the same time. Audit runs: 52 events each, all checks pass, and two philosophers eating at once in every run.

Screenshots of the four supplied replays are in `screenshots/`. Each screenshot is a snapshot at a stated event number in the matching replay.

## Timeouts

| Program | Thread join | If a deadlock occurs |
|---------|-------------|----------------------|
| Q1 Readers-Writers (semaphore) | `join()` with no timeout (confirmed from the source code; some notes about this run mention a 60 s limit, but the code has none) | The program does not finish; it waits forever |
| Q2 Readers-Writers (monitor) | 60 s limit (`JOIN_TIMEOUT`) | Check 7 fails and the result is reported |
| Q3 Dining Philosophers (semaphore) | 60 s limit (`JOIN_TIMEOUT`) | The no-deadlock check fails and the result is reported |
| Q4 Dining Philosophers (monitor) | 60 s limit (`JOIN_TIMEOUT`) | The no-deadlock check fails and the result is reported |

This is the only Q1 difference from the other three. Q1 is written to wait for every thread, so a deadlock there would stop the program instead of being reported.

## Known limitations

- Thread scheduling is not deterministic, so event order, the maximum concurrency and the held-back counts differ between runs.
- Concurrency figures (readers overlapping, philosophers eating together) depend on timing. They are shown as information, not as pass or fail.
- The programs use `time.sleep` and random delays to make interleavings visible. Python runs one thread at a time in the interpreter, so the programs show logical interleaving, not parallel speed-up.
- In Q4 the RELEASING state is logged inside the monitor and is instantaneous, so it is only a sliver on the timeline.
- Timestamps are whole milliseconds, so several events can share one timestamp.
- The number of philosophers is fixed at four, as the assignment requires. The room size and fork numbering are written for four.
- The repository contains no automated unit tests. Verification is the program's own checks, plus comparison with the replay data.
- Windows was not tested for `run.ps1`.

## AI use and references

AI assistance was used for this assignment. The prompt log is in `ai_prompts/`, and the references are in `references/`.
