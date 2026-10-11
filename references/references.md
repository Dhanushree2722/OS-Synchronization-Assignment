# References

- A. B. Downey, *The Little Book of Semaphores*, 2nd ed. - readers-writers (incl. the
  no-starve turnstile pattern) and dining philosophers solutions.
- E. W. Dijkstra, "Hierarchical ordering of sequential processes", Acta Informatica 1, 1971 -
  original dining philosophers formulation and the state-array monitor idea.
- P. J. Courtois, F. Heymans, D. L. Parnas, "Concurrent control with readers and writers",
  CACM 14(10), 1971 - readers/writers priorities.
- A. Silberschatz, P. B. Galvin, G. Gagne, *Operating System Concepts*, ch. "Synchronization
  Examples" - readers-writers, dining philosophers, monitors.
- Python documentation: `threading` (Lock, Semaphore, Condition), `webbrowser`, `json`.
- D. S. Rao, OS-Synchronization-Assignment (Java), github.com/disha-rao/OS-Synchronization-Assignment -
  read as a reference for the structure of the Java dining-philosophers solutions
  (room semaphore with N-1 permits; monitor with `test(i)`), which the Python versions
  here re-implement. No code was copied from it; the Python programs, the event recording
  and the HTML pages are written from scratch for this submission.
