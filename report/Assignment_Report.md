# Assignment report - Readers-Writers and Dining Philosophers (Python)

## 1. Goal

Implement the two classic synchronization problems twice each - once with semaphores and
once with a monitor - using real threads, prove on each run that the rules were kept, and
visualise the actual execution in a browser.

## 2. Common structure

Each program has the same shape:

1. a few settings at the top (number of threads, rounds/meals, delay ranges);
2. the synchronization objects (semaphores or a monitor class);
3. `record(...)`: appends an event `{t, who, state, snapshot..., note}` to a list that is
   protected by its own lock. It is called at the exact point where the synchronization
   state changes and while that state's lock is still held, so the snapshot is exact;
4. the thread functions;
5. `check_results()`: a handful of rule checks computed from what was recorded;
6. `write_html()`: dumps the events as JSON into an HTML template with the player.

## 3. Q1 - Readers-Writers, semaphores

`mutex(1)` protects `reader_count`. `resource(1)` is the shared data lock: the first
reader in acquires it for the whole group, the last reader out releases it; a writer holds
it alone. `turnstile(1)` is held by a writer from the moment it starts waiting until it
owns `resource`, and every reader passes through it (acquire+release), so readers arriving
after a writer wait behind it.

Logging detail that mattered: "finished reading" (counter drops) and "released resource"
(semaphore released) are two events. The release is done inside the log lock together with
`resource.release()`, so a writer that wakes up because of it cannot log "writing" before
the release is in the log. Every event stores who holds `resource` (free / readers / writer).

Checks: no reader starts while a writer holds the resource, no writer starts while anyone
holds it, final value = writers x rounds, resource free at the end, all threads finished
within the 60 s join limit.

## 4. Q2 - Readers-Writers, monitor

A class with one `Lock` and one `Condition` built on it. State: `active_readers`,
`writer_active`, `waiting_writers`. `start_read` waits while `writer_active or
waiting_writers > 0`; `start_write` increments `waiting_writers`, waits while
`writer_active or active_readers > 0`, then flips the flag. Both exits call
`notify_all()`. The read/write itself runs outside the lock. Policy: writers first.

Checks (8): readers overlapped, no writer/writer overlap, no reader/writer overlap, every
thread finished its rounds, final value, writes 1..N in order (no lost update), all threads
joined within a timeout, monitor state clean at the end.

## 5. Q3 - Dining Philosophers, semaphores

`fork[i] = Semaphore(1)` for i in 0..3, `room = Semaphore(3)`. A philosopher goes
THINKING -> HUNGRY (waits for `room`) -> ACQUIRING (left fork, short pause, right fork) ->
EATING -> RELEASING (forks put down, logged before the release so a neighbour's pick-up is
logged after) -> THINKING. With at most three competitors and four forks one of them can
always take both, so the circular wait cannot close.

Checks (7): no deadlock (all threads joined), everyone ate MEALS times, a fork was never
held by two, neighbours never ate together / nobody ate without both forks, never more than
3 in the room, all forks free at the end, plus an information line for the maximum number
eating at once.

## 6. Q4 - Dining Philosophers, monitor

Dijkstra's solution: `state[i]`, `fork_owner[f]`, and one `Condition` per philosopher on a
shared lock. `test(i)` grants both forks atomically when `i` is hungry and neither
neighbour eats, and notifies `i`. `pick_up` sets HUNGRY, calls `test`, and waits in a
`while` until EATING. `put_down` sets THINKING, frees both forks, and calls `test` on both
neighbours. No hold-and-wait, so no deadlock. The RELEASING step is inside the monitor and
has no duration.

Checks (6): no deadlock, everyone ate, fork never granted while held, neighbours never ate
together, information line for max eating at once, monitor state clean at the end.

## 7. Results

Three runs per program with the default settings:

| Program | Events | Key result (from the committed replay) | Time |
|---------|--------|-----------------------------------------|------|
| Q1 semaphores | 96 | value 6/6, no overlap, 12 releases, max 5 readers at once | 4.1 s |
| Q2 monitor | 84 | all 8 checks pass, 5 of 15 reader requests held back for a writer | 4.0 s |
| Q3 semaphores | 112 | all 7 checks pass, max 3 in room, all ate 3x (max eating 1 in this run) | 5-8 s |
| Q4 monitor | 52 | all 6 checks pass, all ate 3x, 2 eating at once observed | 4.4-4.8 s |

The generated pages were also checked in a headless browser: the state recomputed from
the event order matches the recorded snapshots at every event, and the cards, resource /
fork panels, log row and timeline cursor agree at every step.

## 8. Limitations

Python's `Semaphore` / `Condition` are not FIFO, so none of the four claims strict
starvation freedom (see README). Event order is non-deterministic between runs. The
"overlap observed" lines depend on timing and are informational.
