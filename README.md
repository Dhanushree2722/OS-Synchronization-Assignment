# OS Synchronization Assignment (Python)

Readers-Writers and Dining Philosophers, each solved with semaphores and with a monitor.
Every program runs real threads, records what happens, checks the rules and generates a
self-contained `simulation.html` that replays the recorded run.

| # | Problem | Technique | Program |
|---|---------|-----------|---------|
| 1 | Readers-Writers | Semaphores (mutex, resource, turnstile) | `readers_writers/semaphore/readers_writers.py` |
| 2 | Readers-Writers | Monitor (Lock + Condition, writer preference) | `readers_writers/monitor/readers_writers_monitor.py` |
| 3 | Dining Philosophers (4) | Semaphores (fork[i] + room = N-1) | `dining_philosophers/semaphore/dining_philosophers_semaphore.py` |
| 4 | Dining Philosophers (4) | Monitor (Dijkstra state array, condition per philosopher) | `dining_philosophers/monitor/dining_philosophers_monitor.py` |

Run any of them with `python <file>.py` (Python 3, standard library only). The program prints the
event log and its checks, writes `simulation.html` next to itself and opens it in the browser
(`--no-browser` skips that for Q2-Q4). Settings are at the top of each file.
