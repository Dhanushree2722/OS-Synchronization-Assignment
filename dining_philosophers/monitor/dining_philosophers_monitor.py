"""
Q4 - Dining Philosophers (4) with a monitor
(Python version of the Java DiningPhilosophersMonitor program)

Idea (Dijkstra): instead of taking forks one at a time, a philosopher asks the
monitor for both forks together. The monitor says yes only if neither
neighbour is eating. Since the two forks are taken all-or-nothing, nobody ever
holds one fork while waiting for the other - so no hold-and-wait, no deadlock.

            P0
        F0      F1          fork i is the LEFT fork of philosopher i,
     P3            P1       fork (i+1)%4 is the RIGHT one
        F3      F2
            P2

The monitor is a class with one lock and one threading.Condition per
philosopher (all on the same lock). State kept inside, lock always held:
  state[i]       THINKING / HUNGRY / EATING
  fork_owner[f]  -1 = free, else who holds fork f
  self_cv[i]     where philosopher i sleeps while hungry

  pick_up(i):   state[i]=HUNGRY, test(i), then wait until state[i]==EATING
  put_down(i):  state[i]=THINKING, free the forks, test(left), test(right)
  test(i):      if i is hungry and both neighbours aren't eating ->
                state[i]=EATING, give both forks, notify i

Starvation: this is deadlock-free but not starvation-free in theory - if my two
neighbours keep alternating, one of them is always eating and I never get a
turn. It doesn't happen with the random delays here; meals per philosopher are
printed to check. A fix would be to serve the longest-waiting philosopher first.

RELEASING happens inside the monitor so it takes basically no time - it shows
in the log but is only a sliver on the timeline. That's expected.

Run:  python dining_philosophers_monitor.py            (opens simulation.html)
      python dining_philosophers_monitor.py --no-browser

Standard library only.
"""

import json
import os
import random
import sys
import threading
import time
import webbrowser

# ------------------------------------------------------------------
# Settings. Change these during the viva and run again.
# ------------------------------------------------------------------
N = 4                        # philosophers (and forks); the assignment fixes this to 4
MEALS = 3                    # how many times each philosopher wants to eat
THINK_TIME = (0.20, 0.80)    # seconds spent thinking
EAT_TIME = (0.40, 0.80)      # seconds spent eating (critical section)
JOIN_TIMEOUT = 60.0          # if the threads are not done by then, we call it a deadlock
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation.html")

meals_eaten = [0] * N        # each philosopher only writes its own cell

# ------------------------------------------------------------------
# Event recording. Every state change goes into `events`; the HTML page
# at the end is built only from this list.
# ------------------------------------------------------------------
events = []
log_lock = threading.Lock()          # several threads append, so the list needs its own lock
start_time = time.perf_counter()
observed = {"max_eating": 0}
violations = []


def left_fork(i):
    return i


def right_fork(i):
    return (i + 1) % N


def record(mon, pid, state, note=""):
    """Store one event with a snapshot of the monitor's state.

    Always called with the monitor lock held, so state[] and fork_owner[] are
    exactly what the monitor sees at this instant.
    """
    with log_lock:
        if state == "EATING":
            l, r = (pid - 1) % N, (pid + 1) % N
            if mon.state[l] == "EATING" or mon.state[r] == "EATING":
                violations.append(f"P{pid} started eating while a neighbour was eating")
            if mon.fork_owner[left_fork(pid)] != pid or mon.fork_owner[right_fork(pid)] != pid:
                violations.append(f"P{pid} started eating without owning both forks")
        observed["max_eating"] = max(observed["max_eating"], mon.state.count("EATING"))
        t_ms = round((time.perf_counter() - start_time) * 1000)
        events.append({
            "t": t_ms,
            "who": pid,
            "kind": "state",
            "state": state,
            "forks": list(mon.fork_owner),
            "eating": mon.state.count("EATING"),
            "in_room": 0,
            "note": note,
        })
        forks_txt = " ".join(f"F{i}:{'-' if o == -1 else 'P' + str(o)}" for i, o in enumerate(mon.fork_owner))
        print(f"[{t_ms:6d} ms] P{pid} {state:<9} {forks_txt}  {note}")


# ------------------------------------------------------------------
# The monitor
# ------------------------------------------------------------------
class TableMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = ["THINKING"] * N
        self.fork_owner = [-1] * N
        self.self_cv = [threading.Condition(self.lock) for _ in range(N)]   # one per philosopher

    def _test(self, i):
        """Called ONLY with the lock held. If i is hungry and no neighbour eats, let him eat."""
        l, r = (i - 1) % N, (i + 1) % N
        if self.state[i] == "HUNGRY" and self.state[l] != "EATING" and self.state[r] != "EATING":
            fl, fr = left_fork(i), right_fork(i)
            if self.fork_owner[fl] != -1 or self.fork_owner[fr] != -1:
                violations.append(f"monitor granted P{i} a fork that was still held")
            # grant BOTH forks atomically - this is what prevents hold-and-wait
            self.fork_owner[fl] = i
            self.fork_owner[fr] = i
            self.state[i] = "EATING"
            record(self, i, "EATING", f"monitor grants both forks F{fl} and F{fr} at once")
            self.self_cv[i].notify()           # wake philosopher i if he is sleeping

    def pick_up(self, i):
        """Philosopher i wants to eat. Blocks until both forks are granted."""
        with self.lock:                        # ENTER the monitor
            self.state[i] = "HUNGRY"
            record(self, i, "HUNGRY", "is hungry, asks the monitor for both forks")
            self._test(i)                      # maybe we can eat right away
            # `while`, not `if`: re-check after every wake-up.
            while self.state[i] != "EATING":
                self.self_cv[i].wait()         # releases the lock while sleeping
        # LEAVE the monitor - the eating itself happens outside the lock

    def put_down(self, i):
        """Philosopher i finished eating: give the forks back and help the neighbours."""
        with self.lock:
            fl, fr = left_fork(i), right_fork(i)
            self.state[i] = "THINKING"         # done eating (so the eating count drops now) ...
            record(self, i, "RELEASING", "finished eating, putting forks down")
            self.fork_owner[fl] = -1           # ... but the forks are only freed here
            self.fork_owner[fr] = -1
            record(self, i, "THINKING", f"released forks F{fl} and F{fr}, back to thinking")
            self._test((i - 1) % N)            # maybe the left neighbour can eat now
            self._test((i + 1) % N)            # maybe the right neighbour can eat now


table = TableMonitor()


# ------------------------------------------------------------------
# The philosopher thread
# ------------------------------------------------------------------
def philosopher(pid):
    with table.lock:
        record(table, pid, "THINKING", "sits down and starts thinking")
    for _ in range(MEALS):
        time.sleep(random.uniform(*THINK_TIME))      # THINK (non-critical)
        table.pick_up(pid)                           # ENTRY: may block until forks are granted
        time.sleep(random.uniform(*EAT_TIME))        # EAT: critical section, lock NOT held, forks are ours
        meals_eaten[pid] += 1
        table.put_down(pid)                          # EXIT: release forks, wake neighbours


# ------------------------------------------------------------------
# Checks
# ------------------------------------------------------------------
def check_results(threads, elapsed):
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("1. no deadlock: every philosopher thread finished",
          not any(t.is_alive() for t in threads), f"{elapsed:.2f} s, limit {JOIN_TIMEOUT} s")
    check("2. no starvation in this run: everyone ate MEALS times",
          all(m == MEALS for m in meals_eaten), "meals " + ", ".join(f"P{i}={m}" for i, m in enumerate(meals_eaten)))
    check("3. a fork was never granted while still held",
          not any("still held" in v for v in violations))
    check("4. neighbours never ate at the same time / nobody ate without both forks",
          not any("neighbour" in v or "without owning" in v for v in violations))
    # Informational only: at most 2 of 4 can eat together; whether it happens is up to scheduling.
    check("5. (info) max philosophers eating at the same time",
          True, f"max eating at once = {observed['max_eating']} (2 = two non-neighbours overlapped)")
    check("6. monitor back in a consistent final state (all thinking, all forks free)",
          all(s == "THINKING" for s in table.state) and all(o == -1 for o in table.fork_owner),
          f"state={table.state} forks={table.fork_owner}")

    print("\n---- checks ----")
    for c in checks:
        print(f"{'PASS' if c['ok'] else 'FAIL'}  {c['name']}  {c['detail']}")
    for v in violations:
        print("  !!", v)
    all_ok = all(c["ok"] for c in checks) and not violations
    print("RESULT:", "all checks passed - no deadlock occurred" if all_ok else "FAILED")
    return {"checks": checks, "violations": violations, "all_ok": all_ok}


# ------------------------------------------------------------------
# HTML generation. Everything the page shows comes from `events`.
# ------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__ - execution replay</title>
<style>
  body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f6f9; color: #222; }
  header { background: #3b2d55; color: #fff; padding: 14px 22px; }
  header h1 { margin: 0 0 4px; font-size: 20px; }
  header .sub { font-size: 13px; opacity: .9; }
  .ok { color: #7CFC9A; font-weight: bold; } .bad { color: #ff8a80; font-weight: bold; }
  main { padding: 16px 22px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .wide { grid-column: 1 / -1; }
  .card { background: #fff; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card h2 { margin: 0 0 10px; font-size: 15px; color: #3b2d55; }
  .controls button, .controls select { font-size: 14px; padding: 6px 12px; margin-right: 6px; }
  .procs { display: flex; flex-wrap: wrap; gap: 8px; }
  .proc { width: 150px; border-radius: 6px; padding: 8px; border: 2px solid #ccc; background: #eee; text-align: center; }
  .proc b { display: block; font-size: 16px; }
  .proc small { display: block; font-size: 11px; min-height: 28px; color: #444; }
  .THINKING { background: #ececec; border-color: #ccc; }
  .HUNGRY { background: #fff3cd; border-color: #e0b400; }
  .ACQUIRING { background: #ffe5cc; border-color: #fd7e14; }
  .EATING { background: #d4edda; border-color: #28a745; }
  .RELEASING { background: #cfe2ff; border-color: #0d6efd; }
  .forks { display: flex; gap: 8px; }
  .forkbox { flex: 1; border-radius: 6px; padding: 8px; text-align: center; border: 2px solid #bbb; background: #f8f8f8; }
  .forkbox.held { background: #f8d7da; border-color: #dc3545; }
  .legend span { display: inline-block; padding: 2px 8px; margin-right: 6px; border-radius: 4px; font-size: 12px; border: 1px solid #aaa; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { padding: 3px 6px; border-bottom: 1px solid #e3e3e3; text-align: left; }
  th { background: #eef2f7; position: sticky; top: 0; }
  tr.cur { background: #fff3cd; font-weight: bold; }
  tr.done { color: #666; }
  #log { max-height: 320px; overflow: auto; }
  .gantt { position: relative; }
  .grow { display: flex; align-items: center; height: 22px; margin: 3px 0; }
  .grow .lbl { width: 34px; font-weight: bold; font-size: 13px; }
  .gtrack { position: relative; flex: 1; height: 18px; background: #f0f0f0; border-radius: 3px; }
  .seg { position: absolute; top: 0; height: 100%; border-radius: 3px; opacity: .9; }
  .seg.HUNGRY { background: #e0b400; } .seg.ACQUIRING { background: #fd7e14; } .seg.EATING { background: #28a745; }
  .seg.RELEASING { background: #0d6efd; } .seg.F { background: #dc3545; }
  #cursor { position: absolute; top: 0; bottom: 0; width: 2px; background: #000; left: 34px; }
  .axis { margin-left: 34px; font-size: 11px; color: #666; display: flex; justify-content: space-between; }
  ul.checks { margin: 0; padding-left: 18px; font-size: 13px; }
  #alert { color: #dc3545; font-weight: bold; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__ (replay of a real run)</h1>
  <div class="sub">__SUBTITLE__<br>__SUMMARY__</div>
</header>
<main>
  <div class="card wide controls">
    <button id="play">Play</button>
    <button id="step">Step</button>
    <button id="reset">Reset</button>
    speed <select id="speed"><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="2">2x</option><option value="4">4x</option></select>
    &nbsp; clock: <b id="clock">0 ms</b> &nbsp; event <b id="count">0</b> / __NEVENTS__ &nbsp; <span id="alert"></span>
    <span class="legend" style="float:right">
      <span class="THINKING">thinking</span><span class="HUNGRY">hungry</span><span class="EATING">eating</span><span class="RELEASING">releasing</span>
    </span>
  </div>

  <div class="card wide"><h2>Philosophers</h2><div class="procs" id="phils"></div></div>
  <div class="card"><h2>Forks (shared resources)</h2><div class="forks" id="forks"></div></div>
  <div class="card"><h2>Table state</h2><div id="table"></div></div>

  <div class="card wide"><h2>Timeline (P rows: philosopher state; F rows: red = fork in use)</h2>
    <div class="gantt" id="gantt"></div><div class="axis"><span>0 ms</span><span id="tmax"></span></div></div>

  <div class="card wide"><h2>Event log recorded by the program</h2><div id="log"></div></div>
  <div class="card wide"><h2>Checks run by the program</h2><ul class="checks">__CHECKS__</ul></div>
</main>
<script>
const EVENTS = __EVENTS__;
const CFG = __CONFIG__;
const N = CFG.philosophers;

let idx = -1, timer = null, speed = 1;
const st = [];

function reset() {
  clearTimeout(timer); timer = null; idx = -1;
  for (let i = 0; i < N; i++) st[i] = { state: "THINKING", note: "" };
  document.getElementById("play").textContent = "Play";
  render();
}
function applyNext() {
  if (idx >= EVENTS.length - 1) return false;
  idx++;
  const e = EVENTS[idx];
  st[e.who] = { state: e.state, note: e.note };
  render();
  return true;
}
function tick() {
  if (!applyNext()) { pause(); return; }
  const nxt = EVENTS[idx + 1];
  if (!nxt) { pause(); return; }
  timer = setTimeout(tick, Math.max(20, (nxt.t - EVENTS[idx].t) / speed));
}
function play() { if (timer) return; document.getElementById("play").textContent = "Pause"; tick(); }
function pause() { clearTimeout(timer); timer = null; document.getElementById("play").textContent = "Play"; }

function render() {
  const cur = idx >= 0 ? EVENTS[idx] : null;
  const forks = cur ? cur.forks : Array(N).fill(-1);
  document.getElementById("clock").textContent = (cur ? cur.t : 0) + " ms";
  document.getElementById("count").textContent = idx + 1;

  let h = "";
  for (let i = 0; i < N; i++) {
    const s = st[i];
    h += `<div class="proc ${s.state}"><b>P${i}</b>${s.state.toLowerCase()}<small>${s.note}</small></div>`;
  }
  document.getElementById("phils").innerHTML = h;

  // Fork ownership comes straight from the snapshot stored in the event, i.e.
  // exactly what the monitor recorded when it granted or freed the forks.
  h = "";
  for (let i = 0; i < N; i++) h += `<div class="forkbox ${forks[i] >= 0 ? "held" : ""}"><b>F${i}</b><br>${forks[i] >= 0 ? "held by P" + forks[i] : "free"}</div>`;
  document.getElementById("forks").innerHTML = h;

  const eating = st.map((s, i) => s.state === "EATING" ? "P" + i : null).filter(Boolean);
  const hungry = st.map((s, i) => s.state === "HUNGRY" || s.state === "ACQUIRING" ? "P" + i : null).filter(Boolean);
  document.getElementById("table").innerHTML =
    `eating now: <b>${eating.length ? eating.join(", ") : "nobody"}</b> (${cur ? cur.eating : 0})<br>` +
    `hungry (waiting in the monitor): ${hungry.length ? hungry.join(", ") : "nobody"}<br>` +
    `forks in use: ${forks.filter(f => f >= 0).length} / ${N}`;
  // Deadlock would look like: every fork held and every holder still waiting for
  // another fork. (A philosopher who is RELEASING still holds forks for a moment,
  // but is about to free them, so that is not a deadlock.)
  const holders = [...new Set(forks.filter(f => f >= 0))];
  const allHeld = forks.every(f => f >= 0) && holders.every(h => st[h].state === "ACQUIRING");
  document.getElementById("alert").textContent = allHeld ? "DEADLOCK PATTERN: all forks held, everyone waiting" : "";

  const rows = document.querySelectorAll("#log tr[data-i]");
  rows.forEach(r => { const i = +r.dataset.i; r.className = i === idx ? "cur" : (i < idx ? "done" : ""); });
  if (cur) { const r = rows[idx]; if (r) r.scrollIntoView({ block: "nearest" }); }
  placeCursor(cur ? cur.t : 0);
}

// Cursor: plain pixel arithmetic (34px label column + fraction of the track).
function placeCursor(t) {
  const gantt = document.getElementById("gantt"), cursor = document.getElementById("cursor");
  if (!cursor) return;
  const trackWidth = Math.max(0, gantt.clientWidth - 34);
  const frac = TMAX > 0 ? Math.min(1, Math.max(0, t / TMAX)) : 0;
  cursor.style.left = Math.round(34 + frac * trackWidth) + "px";
}
window.addEventListener("resize", () => placeCursor(idx >= 0 ? EVENTS[idx].t : 0));

// ---- static parts built once: event table + gantt ----
const TMAX = EVENTS.length ? EVENTS[EVENTS.length - 1].t : 0;
const SPAN = TMAX || 1;
document.getElementById("tmax").textContent = TMAX + " ms";
(function buildLog() {
  let h = "<table><tr><th>#</th><th>time</th><th>who</th><th>state</th>";
  for (let i = 0; i < N; i++) h += `<th>F${i}</th>`;
  h += "<th>eating</th><th>note</th></tr>";
  EVENTS.forEach((e, i) => {
    h += `<tr data-i="${i}"><td>${i + 1}</td><td>${e.t} ms</td><td>P${e.who}</td><td>${e.state}</td>`;
    e.forks.forEach(f => h += `<td>${f >= 0 ? "P" + f : "-"}</td>`);
    h += `<td>${e.eating}</td><td>${e.note || ""}</td></tr>`;
  });
  document.getElementById("log").innerHTML = h + "</table>";
})();
(function buildGantt() {
  const segs = {}, open = {};
  const names = [];
  for (let i = 0; i < N; i++) names.push("P" + i);
  for (let i = 0; i < N; i++) names.push("F" + i);
  names.forEach(n => segs[n] = []);
  let prevForks = Array(N).fill(-1);
  for (const e of EVENTS) {
    const k = "P" + e.who;
    if (e.kind === "state") {
      if (open[k]) { segs[k].push({ ...open[k], e: e.t }); delete open[k]; }
      if (e.state !== "THINKING") open[k] = { s: e.t, c: e.state };
    }
    for (let f = 0; f < N; f++) {
      if (e.forks[f] !== prevForks[f]) {
        const fk = "F" + f;
        if (open[fk]) { segs[fk].push({ ...open[fk], e: e.t }); delete open[fk]; }
        if (e.forks[f] >= 0) open[fk] = { s: e.t, c: "F" };
      }
    }
    prevForks = e.forks;
  }
  let h = "";
  for (const n of names) {
    h += `<div class="grow"><span class="lbl">${n}</span><div class="gtrack">`;
    for (const s of segs[n]) h += `<div class="seg ${s.c}" style="left:${s.s / SPAN * 100}%;width:${Math.max(0.3, (s.e - s.s) / SPAN * 100)}%" title="${s.c} ${s.s}-${s.e} ms"></div>`;
    h += "</div></div>";
  }
  document.getElementById("gantt").innerHTML = h + '<div id="cursor"></div>';
})();

document.getElementById("play").onclick = () => timer ? pause() : play();
document.getElementById("step").onclick = () => { pause(); applyNext(); };
document.getElementById("reset").onclick = reset;
document.getElementById("speed").onchange = e => speed = +e.target.value;
reset();
</script>
</body>
</html>
"""


def write_html(summary, open_browser):
    verdict = ('<span class="ok">all checks passed - no deadlock</span>' if summary["all_ok"]
               else '<span class="bad">FAILED: ' + "; ".join(c["name"] for c in summary["checks"] if not c["ok"]) + "</span>")
    text = (f"{N} philosophers, {MEALS} meals each | {len(events)} events recorded | "
            f"meals: " + ", ".join(f"P{i}={m}" for i, m in enumerate(meals_eaten)) + f" | {verdict}")
    checks_html = "".join(f"<li>{'PASS' if c['ok'] else 'FAIL'} - {c['name']} <i>{c['detail']}</i></li>" for c in summary["checks"])
    config = {"philosophers": N, "meals": MEALS, "room": False}
    html = (HTML_TEMPLATE
            .replace("__TITLE__", "Dining Philosophers (4) - Monitor Solution")
            .replace("__SUBTITLE__", "Monitor = one lock + a condition variable per philosopher; both forks granted atomically (no hold-and-wait -> no deadlock)")
            .replace("__EVENTS__", json.dumps(events))
            .replace("__CONFIG__", json.dumps(config))
            .replace("__SUMMARY__", text)
            .replace("__CHECKS__", checks_html)
            .replace("__NEVENTS__", str(len(events))))
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML written to {HTML_FILE}")
    if open_browser:
        webbrowser.open("file:///" + HTML_FILE.replace(os.sep, "/"))


def main():
    open_browser = "--no-browser" not in sys.argv
    print(f"=== Dining Philosophers (MONITOR): philosophers={N} meals each={MEALS} ===\n")
    threads = [threading.Thread(target=philosopher, args=(i,), name=f"P{i}") for i in range(N)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    deadline = t0 + JOIN_TIMEOUT
    for t in threads:
        t.join(max(0.0, deadline - time.perf_counter()))     # a deadlock would leave threads alive
    elapsed = time.perf_counter() - t0

    print("\nProgram finished =>", "no deadlock occurred." if not any(t.is_alive() for t in threads) else "THREADS STILL BLOCKED (deadlock?)")
    for i in range(N):
        print(f"  P{i} ate {meals_eaten[i]} time(s)" + ("  (no starvation)" if meals_eaten[i] == MEALS else "  (STARVED?)"))
    summary = check_results(threads, elapsed)
    write_html(summary, open_browser)


if __name__ == "__main__":
    main()
