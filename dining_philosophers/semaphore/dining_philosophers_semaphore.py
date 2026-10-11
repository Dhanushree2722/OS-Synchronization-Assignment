"""
Q3 - Dining Philosophers (4) with semaphores


4 philosophers around a table, one fork between each pair, so 4 forks.
To eat you need both your left and right fork.

            P0
        F0      F1          fork i is the LEFT fork of philosopher i,
     P3            P1       fork (i+1)%4 is the RIGHT one
        F3      F2
            P2

Semaphores:
  fork[0..3] = Semaphore(1)   one per fork, 1 = free
  room       = Semaphore(3)   only 3 philosophers may try for forks at once

Why the simple version deadlocks: everyone grabs the left fork, then waits for
the right one. If all 4 do that together, each holds one fork and waits for the
neighbour -> circular wait, nobody eats.

Fix used here: at most N-1 = 3 compete. With 4 forks and 3 competitors one of
them always gets both (pigeonhole), so the circle can't close. That removes the
circular-wait condition, so no deadlock.

Starvation: the Java version used fair (FIFO) semaphores. Python's Semaphore
isn't FIFO, so in theory someone could keep getting overtaken. With the random
delays it doesn't happen; the program counts meals per philosopher so you can
see that everyone ate.

Run:  python dining_philosophers_semaphore.py            (opens simulation.html)
      python dining_philosophers_semaphore.py --no-browser

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
PICKUP_PAUSE = (0.05, 0.15)  # small pause between taking the two forks (makes interleaving visible)
JOIN_TIMEOUT = 60.0          # if the threads are not done by then, we call it a deadlock
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation.html")

# ------------------------------------------------------------------
# Synchronisation variables
# ------------------------------------------------------------------
fork = [threading.Semaphore(1) for _ in range(N)]   # one binary semaphore per fork
room = threading.Semaphore(N - 1)                   # at most N-1 philosophers compete -> no deadlock

meals_eaten = [0] * N                               # each philosopher only writes its own cell

# ------------------------------------------------------------------
# Event recording. Every state change goes into `events`; the HTML page
# at the end is built only from this list.
# ------------------------------------------------------------------
events = []
log_lock = threading.Lock()          # several threads append, so the list needs its own lock
start_time = time.perf_counter()

# bookkeeping used only to double-check the rules while the program runs
fork_owner = [-1] * N                # -1 = free, otherwise philosopher id (updated at the logged moments)
phil_state = ["THINKING"] * N
observed = {"in_room": 0, "max_in_room": 0, "max_eating": 0}
violations = []


def left_fork(i):
    return i


def right_fork(i):
    return (i + 1) % N


def record(pid, state, note="", fork_id=None, owner=None):
    """Store one event. state is a philosopher state or 'FORK' for a fork change.

    fork_id/owner: when a fork is picked up (owner = pid) or put down (owner = -1).
    The rule checks run here, at the moment the thread really changes state.
    """
    with log_lock:
        if fork_id is not None:
            if owner != -1 and fork_owner[fork_id] != -1:
                violations.append(f"P{pid} took fork F{fork_id} while P{fork_owner[fork_id]} still held it")
            fork_owner[fork_id] = owner
        else:
            if state == "EATING":
                l, r = (pid - 1) % N, (pid + 1) % N
                if phil_state[l] == "EATING" or phil_state[r] == "EATING":
                    violations.append(f"P{pid} started eating while a neighbour was eating")
                if fork_owner[left_fork(pid)] != pid or fork_owner[right_fork(pid)] != pid:
                    violations.append(f"P{pid} started eating without holding both forks")
            if state == "ACQUIRING":
                observed["in_room"] += 1
                observed["max_in_room"] = max(observed["max_in_room"], observed["in_room"])
                if observed["in_room"] > N - 1:
                    violations.append(f"{observed['in_room']} philosophers in the room (limit {N - 1})")
            if state == "THINKING" and phil_state[pid] == "RELEASING":
                observed["in_room"] -= 1     # logged just before room.release(), so the count never lags
            phil_state[pid] = state
            observed["max_eating"] = max(observed["max_eating"], phil_state.count("EATING"))

        t_ms = round((time.perf_counter() - start_time) * 1000)
        events.append({
            "t": t_ms,
            "who": pid,
            "kind": "fork" if fork_id is not None else "state",
            "state": phil_state[pid],
            "forks": list(fork_owner),
            "eating": phil_state.count("EATING"),
            "in_room": observed["in_room"],
            "note": note,
        })
        forks_txt = " ".join(f"F{i}:{'-' if o == -1 else 'P' + str(o)}" for i, o in enumerate(fork_owner))
        print(f"[{t_ms:6d} ms] P{pid} {phil_state[pid]:<9} {forks_txt}  {note}")


# ------------------------------------------------------------------
# The philosopher thread
# ------------------------------------------------------------------
def philosopher(pid):
    left, right = left_fork(pid), right_fork(pid)
    record(pid, "THINKING", "sits down and starts thinking")
    for meal in range(1, MEALS + 1):
        # ---------- THINK (non-critical) ----------
        time.sleep(random.uniform(*THINK_TIME))

        # ---------- HUNGRY: wants to eat ----------
        record(pid, "HUNGRY", f"is hungry (meal {meal}), waiting for a place at the table")
        room.acquire()                 # at most 3 pass; the 4th blocks here (deadlock prevention)

        # ---------- ACQUIRING FORKS ----------
        record(pid, "ACQUIRING", f"entered the room, trying to take forks F{left} and F{right}")
        fork[left].acquire()                                   # wait() on the left fork
        record(pid, "ACQUIRING", f"picked up left fork F{left}", fork_id=left, owner=pid)
        time.sleep(random.uniform(*PICKUP_PAUSE))              # small pause: makes interleaving visible
        fork[right].acquire()                                  # wait() on the right fork
        record(pid, "ACQUIRING", f"picked up right fork F{right}", fork_id=right, owner=pid)

        # ---------- EAT (critical section: uses both forks exclusively) ----------
        record(pid, "EATING", f"has both forks F{left} and F{right} and eats")
        time.sleep(random.uniform(*EAT_TIME))
        meals_eaten[pid] += 1

        # ---------- RELEASING FORKS ----------
        record(pid, "RELEASING", "finished eating, putting forks down")
        # "fork is free" is logged BEFORE the release on purpose: the neighbour
        # can only pick it up after release(), so its pick-up is logged after.
        record(pid, "RELEASING", f"put down left fork F{left}", fork_id=left, owner=-1)
        fork[left].release()                                   # signal() left fork
        record(pid, "RELEASING", f"put down right fork F{right}", fork_id=right, owner=-1)
        fork[right].release()                                  # signal() right fork
        record(pid, "THINKING", "back to thinking, leaving the room")
        room.release()                                         # leave the room: another philosopher may enter


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
    check("3. a fork was never held by two philosophers",
          not any("took fork" in v for v in violations))
    check("4. neighbours never ate at the same time / nobody ate without both forks",
          not any("neighbour" in v or "without holding" in v for v in violations))
    check(f"5. at most N-1 = {N - 1} philosophers in the room at once",
          not any("in the room" in v for v in violations), f"max in room = {observed['max_in_room']}")
    # Informational only: with 4 philosophers at most 2 can eat together, but
    # whether that actually happens depends on scheduling, so it is not a pass/fail rule.
    check("6. (info) max philosophers eating at the same time",
          True, f"max eating at once = {observed['max_eating']} (2 = two non-neighbours overlapped)")
    check("7. all forks free at the end", all(o == -1 for o in fork_owner))

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
      <span class="THINKING">thinking</span><span class="HUNGRY">hungry</span><span class="ACQUIRING">acquiring forks</span><span class="EATING">eating</span><span class="RELEASING">releasing</span>
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
  // exactly what the program recorded when the fork changed hands.
  h = "";
  for (let i = 0; i < N; i++) h += `<div class="forkbox ${forks[i] >= 0 ? "held" : ""}"><b>F${i}</b><br>${forks[i] >= 0 ? "held by P" + forks[i] : "free"}</div>`;
  document.getElementById("forks").innerHTML = h;

  const eating = st.map((s, i) => s.state === "EATING" ? "P" + i : null).filter(Boolean);
  const hungry = st.map((s, i) => s.state === "HUNGRY" || s.state === "ACQUIRING" ? "P" + i : null).filter(Boolean);
  document.getElementById("table").innerHTML =
    `eating now: <b>${eating.length ? eating.join(", ") : "nobody"}</b> (${cur ? cur.eating : 0})<br>` +
    `hungry / acquiring: ${hungry.length ? hungry.join(", ") : "nobody"}<br>` +
    (CFG.room ? `in the room (limit ${N - 1}): <b>${cur ? cur.in_room : 0}</b><br>` : "") +
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
    config = {"philosophers": N, "meals": MEALS, "room": True}
    html = (HTML_TEMPLATE
            .replace("__TITLE__", "Dining Philosophers (4) - Semaphore Solution")
            .replace("__SUBTITLE__", f"Semaphores: fork[0..{N - 1}] = 1 each, room = {N - 1} (at most N-1 philosophers compete -> no deadlock)")
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
    print(f"=== Dining Philosophers (SEMAPHORE): philosophers={N} meals each={MEALS} ===\n")
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
