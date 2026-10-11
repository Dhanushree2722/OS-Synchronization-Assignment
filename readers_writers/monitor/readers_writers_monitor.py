"""
Q2 - Readers-Writers problem with a monitor

Same rules as Q1:
  - many readers can read at the same time
  - only one writer can write at a time
  - nobody reads while a writer is writing

Python has no monitor keyword, so I built one myself: one lock that protects
the shared counters, plus a threading.Condition on that lock so threads can
sleep until something changes. `with lock:` is "enter the monitor",
cond.wait() sleeps and gives the lock back, cond.notify_all() wakes everyone.

The monitor (class ReadersWritersMonitor) keeps three things:
    active_readers   readers reading right now
    writer_active    True while a writer writes
    waiting_writers  writers queued up - this is what gives writers preference
Only the monitor methods touch these, always with the lock held. The actual
read/write of the data happens OUTSIDE the lock between start_x/end_x,
otherwise readers could never overlap.

Policy: writers first. A reader may enter only if no writer is writing and
none is waiting.

Fairness: readers can't starve a writer. Readers themselves CAN starve if
writers keep coming. Which waiting writer wakes first is up to Python /
the OS - Condition doesn't promise FIFO - so I'm not claiming strict
starvation freedom.

Run:  python readers_writers_monitor.py            (opens simulation.html)
      python readers_writers_monitor.py --no-browser

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
NUM_READERS = 5
NUM_WRITERS = 2
ROUNDS = 3                  # how many times each thread reads / writes
READ_TIME = (0.15, 0.40)    # seconds a reader spends reading (random in this range)
WRITE_TIME = (0.25, 0.50)   # seconds a writer spends writing
THINK_TIME = (0.05, 0.60)   # pause between two attempts of the same thread
JOIN_TIMEOUT = 60.0         # seconds we are willing to wait for all threads (check 7)
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation.html")

# ------------------------------------------------------------------
# The shared resource. This is what the monitor protects.
# ------------------------------------------------------------------
shared_data = {"value": 0, "written_by": "nobody yet"}

# ------------------------------------------------------------------
# Event recording. Every state change goes into `events`; the HTML page
# at the end is built only from this list.
# ------------------------------------------------------------------
events = []
log_lock = threading.Lock()           # several threads append, so the list needs its own lock
start_time = time.perf_counter()

# bookkeeping used only to double-check the rules while the program runs
observed = {"max_readers": 0, "writes": [], "done": {}}   # done[label] = finished operations
violations = []


def record(role, pid, state, mon, note="", value=None):
    """Store one event with a snapshot of the monitor's state.

    Called while the caller holds the monitor lock, so active_readers /
    writer_active / waiting_writers are exactly what the monitor sees at this
    instant - the log can never be 'between' two states.
    """
    if mon.writer_active:
        owner = "writer"
    elif mon.active_readers > 0:
        owner = "readers"
    else:
        owner = "free"
    label = ("R" if role == "reader" else "W") + str(pid)

    with log_lock:
        # ---- rule checks happen at the moment of entry (checks 2 and 3) ----
        if state == "reading" and mon.writer_active:
            violations.append(f"{label} started reading while a writer was active")
        if state == "writing" and mon.active_readers > 0:
            violations.append(f"{label} started writing while {mon.active_readers} reader(s) were active")
        if state == "writing" and mon._writers_inside != 1:
            violations.append(f"{label} started writing while another writer was writing")
        if state == "reading":
            observed["max_readers"] = max(observed["max_readers"], mon.active_readers)
        if state in ("finished reading", "finished writing"):
            observed["done"][label] = observed["done"].get(label, 0) + 1
        if state == "finished writing":
            observed["writes"].append(value)

        t_ms = round((time.perf_counter() - start_time) * 1000)
        events.append({
            "t": t_ms,
            "role": role,
            "id": pid,
            "state": state,
            "active_readers": mon.active_readers,
            "writer_active": mon.writer_active,
            "waiting_writers": mon.waiting_writers,
            "resource": owner,
            "value": value,
            "note": note,
        })
        print(f"[{t_ms:6d} ms] {label:<3} {state:<17} readers={mon.active_readers} "
              f"writer={'yes' if mon.writer_active else 'no '} waitingW={mon.waiting_writers} "
              f"resource={owner:<7} {note}")


# ------------------------------------------------------------------
# The monitor
# ------------------------------------------------------------------
class ReadersWritersMonitor:
    """Hands out permission to read or write. All state changes happen with
    the lock held; threads that cannot proceed sleep on the condition."""

    def __init__(self):
        self.lock = threading.Lock()
        # One condition variable is enough: whenever the state changes we wake
        # everybody with notify_all() and each sleeper re-checks its own
        # `while` condition. Simple, and it cannot lose a wake-up.
        self.state_changed = threading.Condition(self.lock)
        self.active_readers = 0
        self.writer_active = False
        self.waiting_writers = 0
        self._writers_inside = 0      # only for the self-check; mirrors writer_active

    # ---------- readers ----------
    def start_read(self, rid):
        with self.lock:
            record("reader", rid, "waiting", self)
            # `while`, not `if`: after being woken another thread may already
            # have changed the state again, so the condition must be re-tested.
            while self.writer_active or self.waiting_writers > 0:
                self.state_changed.wait()
            self.active_readers += 1
            # Reading the value here (lock held) is safe: no writer can be
            # active, and the event then shows exactly what this reader sees.
            value = shared_data["value"]
            record("reader", rid, "reading", self, f"sees value {value}", value)
            return value

    def end_read(self, rid, value):
        with self.lock:
            self.active_readers -= 1
            # The state change IS the release: as soon as active_readers hits 0
            # a waiting writer may proceed. Logged in the same locked step.
            record("reader", rid, "finished reading", self, "", value)
            if self.active_readers == 0:
                self.state_changed.notify_all()

    # ---------- writers ----------
    def start_write(self, wid):
        with self.lock:
            self.waiting_writers += 1          # from now on new readers hold back
            record("writer", wid, "waiting", self)
            while self.writer_active or self.active_readers > 0:
                self.state_changed.wait()
            self.waiting_writers -= 1
            self.writer_active = True
            self._writers_inside += 1
            old = shared_data["value"]
            record("writer", wid, "writing", self, f"changing {old} -> {old + 1}", old)
            return old

    def end_write(self, wid, new_value):
        with self.lock:
            self.writer_active = False
            self._writers_inside -= 1
            record("writer", wid, "finished writing", self, f"value is now {new_value}", new_value)
            # Wake everyone: a queued writer will win (readers re-check
            # waiting_writers and go back to sleep), otherwise readers go.
            self.state_changed.notify_all()


monitor = ReadersWritersMonitor()


# ------------------------------------------------------------------
# The threads
# ------------------------------------------------------------------
def reader(rid):
    """One reader thread. Runs ROUNDS times."""
    for _ in range(ROUNDS):
        time.sleep(random.uniform(*THINK_TIME))      # doing something else
        value = monitor.start_read(rid)              # may block inside the monitor
        # ---- critical section: reading, lock NOT held, other readers may overlap ----
        time.sleep(random.uniform(*READ_TIME))
        # ---- end of critical section ----
        monitor.end_read(rid, value)
        with monitor.lock:
            record("reader", rid, "idle", monitor)


def writer(wid):
    """One writer thread. Runs ROUNDS times."""
    for _ in range(ROUNDS):
        time.sleep(random.uniform(*THINK_TIME))
        old = monitor.start_write(wid)               # blocks until nobody is inside
        # ---- critical section: writing, lock NOT held, but we are the only one inside ----
        time.sleep(random.uniform(*WRITE_TIME))      # slow two-step update on purpose:
        shared_data["value"] = old + 1               # without the monitor this is where a
        shared_data["written_by"] = f"W{wid}"        # lost update would show up
        # ---- end of critical section ----
        monitor.end_write(wid, old + 1)
        with monitor.lock:
            record("writer", wid, "idle", monitor)


# ------------------------------------------------------------------
# Checks
# ------------------------------------------------------------------
def check_results(threads, elapsed):
    """Run the 8 checks, print a verdict, return a summary for the HTML."""
    expected = NUM_WRITERS * ROUNDS
    actual = shared_data["value"]
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("1. several readers read at the same time",
          observed["max_readers"] >= 2, f"max readers at once = {observed['max_readers']} (scheduling dependent)")
    check("2. no writer overlapped another writer",
          not any("another writer" in v for v in violations))
    check("3. no reader/writer overlap",
          not any("started reading while" in v or "reader(s) were active" in v for v in violations))
    expected_done = {f"R{i}": ROUNDS for i in range(1, NUM_READERS + 1)}
    expected_done.update({f"W{i}": ROUNDS for i in range(1, NUM_WRITERS + 1)})
    check("4. every thread finished its ROUNDS operations",
          observed["done"] == expected_done, f"{sum(observed['done'].values())} operations recorded")
    check("5. final value equals number of writes",
          actual == expected, f"value {actual}, expected {expected}, last written by {shared_data['written_by']}")
    check("6. no lost update (writes were 1,2,3,... in order)",
          sorted(observed["writes"]) == list(range(1, expected + 1)), f"writes recorded: {observed['writes']}")
    check("7. all threads finished within the timeout",
          not any(t.is_alive() for t in threads), f"{elapsed:.2f} s, limit {JOIN_TIMEOUT} s")
    check("8. monitor back in a consistent final state",
          monitor.active_readers == 0 and not monitor.writer_active and monitor.waiting_writers == 0,
          f"active_readers={monitor.active_readers} writer_active={monitor.writer_active} waiting_writers={monitor.waiting_writers}")

    print("\n---- checks ----")
    for c in checks:
        print(f"{'PASS' if c['ok'] else 'FAIL'}  {c['name']}  {c['detail']}")
    for v in violations:
        print("  !!", v)
    all_ok = all(c["ok"] for c in checks) and not violations
    print("RESULT:", "all checks passed" if all_ok else "FAILED")
    return {"checks": checks, "violations": violations, "all_ok": all_ok,
            "final_value": actual, "expected_value": expected, "max_readers": observed["max_readers"]}


# ------------------------------------------------------------------
# HTML generation. Everything the page shows comes from `events`.
# ------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Readers-Writers (monitor) - execution replay</title>
<style>
  body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f6f9; color: #222; }
  header { background: #2b3a55; color: #fff; padding: 14px 22px; }
  header h1 { margin: 0 0 4px; font-size: 20px; }
  header .sub { font-size: 13px; opacity: .9; }
  .ok { color: #7CFC9A; font-weight: bold; } .bad { color: #ff8a80; font-weight: bold; }
  main { padding: 16px 22px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .wide { grid-column: 1 / -1; }
  .card { background: #fff; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card h2 { margin: 0 0 10px; font-size: 15px; color: #2b3a55; }
  .controls button, .controls select { font-size: 14px; padding: 6px 12px; margin-right: 6px; }
  .procs { display: flex; flex-wrap: wrap; gap: 8px; }
  .proc { width: 118px; border-radius: 6px; padding: 8px; border: 2px solid #ccc; background: #eee; text-align: center; }
  .proc b { display: block; font-size: 16px; }
  .proc small { display: block; font-size: 11px; min-height: 14px; color: #444; }
  .idle { background: #ececec; border-color: #ccc; }
  .wait { background: #fff3cd; border-color: #e0b400; }
  .active-r { background: #d4edda; border-color: #28a745; }
  .active-w { background: #f8d7da; border-color: #dc3545; }
  .leaving { background: #cfe2ff; border-color: #0d6efd; }
  #resource, #monitor { font-size: 15px; line-height: 1.7; }
  #resource .big { font-size: 28px; font-weight: bold; }
  .free { color: #28a745; } .busy-r { color: #1e7e34; } .busy-w { color: #dc3545; }
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
  .seg.w { background: #e0b400; } .seg.r { background: #28a745; } .seg.x { background: #dc3545; }
  #cursor { position: absolute; top: 0; bottom: 0; width: 2px; background: #000; left: 34px; }
  .axis { margin-left: 34px; font-size: 11px; color: #666; display: flex; justify-content: space-between; }
  ul.checks { margin: 0; padding-left: 18px; font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>Readers-Writers Problem - monitor solution, writer preference (replay of a real run)</h1>
  <div class="sub">__SUMMARY__</div>
</header>
<main>
  <div class="card wide controls">
    <button id="play">Play</button>
    <button id="step">Step</button>
    <button id="reset">Reset</button>
    speed <select id="speed"><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="2">2x</option><option value="4">4x</option></select>
    &nbsp; clock: <b id="clock">0 ms</b> &nbsp; event <b id="count">0</b> / __NEVENTS__
    <span class="legend" style="float:right">
      <span class="idle">idle</span><span class="wait">waiting</span><span class="active-r">reading</span><span class="active-w">writing</span><span class="leaving">finished</span>
    </span>
  </div>

  <div class="card"><h2>Readers</h2><div class="procs" id="readers"></div></div>
  <div class="card"><h2>Writers</h2><div class="procs" id="writers"></div></div>

  <div class="card"><h2>Shared resource (critical section)</h2><div id="resource"></div></div>
  <div class="card"><h2>Monitor state</h2><div id="monitor"></div></div>

  <div class="card wide"><h2>Timeline (RES row = who holds the resource; yellow = waiting, green = reading, red = writing)</h2>
    <div class="gantt" id="gantt"></div><div class="axis"><span>0 ms</span><span id="tmax"></span></div></div>

  <div class="card wide"><h2>Event log recorded by the program</h2><div id="log"></div></div>
  <div class="card wide"><h2>Checks run by the program</h2><ul class="checks">__CHECKS__</ul></div>
</main>
<script>
const EVENTS = __EVENTS__;
const CFG = __CONFIG__;

let idx = -1, timer = null, speed = 1, value = 0, writtenBy = "nobody yet";
const st = {};
const key = e => e.role + e.id;

function reset() {
  clearTimeout(timer); timer = null; idx = -1; value = 0; writtenBy = "nobody yet";
  for (let i = 1; i <= CFG.readers; i++) st["reader" + i] = { state: "idle", note: "" };
  for (let i = 1; i <= CFG.writers; i++) st["writer" + i] = { state: "idle", note: "" };
  document.getElementById("play").textContent = "Play";
  render();
}
function applyNext() {
  if (idx >= EVENTS.length - 1) return false;
  idx++;
  const e = EVENTS[idx];
  st[key(e)] = { state: e.state, note: e.note };
  if (e.state === "finished writing") { value = e.value; writtenBy = "W" + e.id; }
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

function cls(s) {
  if (s === "waiting") return "wait";
  if (s === "reading") return "active-r";
  if (s === "writing") return "active-w";
  if (s.startsWith("finished")) return "leaving";
  return "idle";
}

function render() {
  const cur = idx >= 0 ? EVENTS[idx] : null;
  document.getElementById("clock").textContent = (cur ? cur.t : 0) + " ms";
  document.getElementById("count").textContent = idx + 1;

  let h = "";
  for (let i = 1; i <= CFG.readers; i++) { const s = st["reader" + i];
    h += `<div class="proc ${cls(s.state)}"><b>R${i}</b>${s.state}<small>${s.note}</small></div>`; }
  document.getElementById("readers").innerHTML = h;
  h = "";
  for (let i = 1; i <= CFG.writers; i++) { const s = st["writer" + i];
    h += `<div class="proc ${cls(s.state)}"><b>W${i}</b>${s.state}<small>${s.note}</small></div>`; }
  document.getElementById("writers").innerHTML = h;

  // Everything below comes from the monitor-state snapshot stored in the event
  // (active_readers / writer_active / waiting_writers / resource), so the panel
  // can only ever show states the monitor really was in.
  const readersIn = [], waitingR = [], waitingW = [];
  let writerIn = null;
  for (const k in st) {
    const s = st[k].state, lbl = (k.startsWith("reader") ? "R" : "W") + k.replace(/\D/g, "");
    if (s === "reading") readersIn.push(lbl);
    if (s === "writing") writerIn = lbl;
    if (s === "waiting") (k.startsWith("reader") ? waitingR : waitingW).push(lbl);
  }
  const owner = cur ? cur.resource : "free";
  const nR = cur ? cur.active_readers : 0;
  let status;
  if (owner === "writer") status = `<span class="busy-w">LOCKED FOR WRITING by ${writerIn}</span>`;
  else if (owner === "readers") status = `<span class="busy-r">BEING READ by ${readersIn.join(", ")} (${nR} at once)</span>`;
  else status = `<span class="free">FREE</span>`;
  document.getElementById("resource").innerHTML =
    `status: ${status}<br>value: <span class="big">${value}</span><br>last written by: ${writtenBy}`;
  document.getElementById("monitor").innerHTML =
    `active_readers: <b>${nR}</b><br>writer_active: <b>${cur && cur.writer_active ? "True" : "False"}</b>` +
    `<br>waiting_writers: <b>${cur ? cur.waiting_writers : 0}</b> ${waitingW.length ? "(" + waitingW.join(", ") + ")" : ""}` +
    `<br>readers held back: ${waitingR.length ? waitingR.join(", ") : "none"}`;

  const rows = document.querySelectorAll("#log tr[data-i]");
  rows.forEach(r => { const i = +r.dataset.i; r.className = i === idx ? "cur" : (i < idx ? "done" : ""); });
  if (cur) { const r = rows[idx]; if (r) r.scrollIntoView({ block: "nearest" }); }
  placeCursor(cur ? cur.t : 0);
}

// The cursor is positioned with plain pixel arithmetic (label column is 34px wide,
// the rest of the row is the track). A CSS calc() mixing % and px products is not
// portable, and a zero-length run (TMAX = 0) must not divide by zero.
function placeCursor(t) {
  const gantt = document.getElementById("gantt"), cursor = document.getElementById("cursor");
  if (!cursor) return;
  const trackWidth = Math.max(0, gantt.clientWidth - 34);
  const frac = TMAX > 0 ? Math.min(1, Math.max(0, t / TMAX)) : 0;
  cursor.style.left = Math.round(34 + frac * trackWidth) + "px";
}
window.addEventListener("resize", () => placeCursor(idx >= 0 ? EVENTS[idx].t : 0));

// ---- static parts built once: event table + gantt ----
const TMAX = EVENTS.length ? EVENTS[EVENTS.length - 1].t : 0;   // total run time in ms (0 if nothing happened)
const SPAN = TMAX || 1;                                            // safe divisor for percentages
document.getElementById("tmax").textContent = TMAX + " ms";
(function buildLog() {
  let h = "<table><tr><th>#</th><th>time</th><th>who</th><th>state</th><th>active readers</th><th>writer active</th><th>waiting writers</th><th>resource</th><th>note</th></tr>";
  EVENTS.forEach((e, i) => {
    h += `<tr data-i="${i}"><td>${i + 1}</td><td>${e.t} ms</td><td>${e.role === "reader" ? "R" : "W"}${e.id}</td><td>${e.state}</td><td>${e.active_readers}</td><td>${e.writer_active ? "yes" : "no"}</td><td>${e.waiting_writers}</td><td>${e.resource}</td><td>${e.note || ""}</td></tr>`;
  });
  document.getElementById("log").innerHTML = h + "</table>";
})();
(function buildGantt() {
  const segs = {}, open = {};
  const names = ["resource"];
  for (let i = 1; i <= CFG.readers; i++) names.push("reader" + i);
  for (let i = 1; i <= CFG.writers; i++) names.push("writer" + i);
  names.forEach(n => segs[n] = []);
  let prevOwner = "free";
  for (const e of EVENTS) {
    if (e.resource !== prevOwner) {
      if (open.resource) { segs.resource.push({ ...open.resource, e: e.t }); delete open.resource; }
      if (e.resource !== "free") open.resource = { s: e.t, c: e.resource === "readers" ? "r" : "x" };
      prevOwner = e.resource;
    }
    const k = key(e);
    if (e.state === "waiting") open[k] = { s: e.t, c: "w" };
    else if (e.state === "reading" || e.state === "writing") {
      if (open[k]) segs[k].push({ ...open[k], e: e.t });
      open[k] = { s: e.t, c: e.state === "reading" ? "r" : "x" };
    } else if (e.state.startsWith("finished")) {
      if (open[k]) { segs[k].push({ ...open[k], e: e.t }); delete open[k]; }
    }
  }
  let h = "";
  for (const n of names) {
    const lbl = n === "resource" ? "RES" : (n.startsWith("reader") ? "R" : "W") + n.replace(/\D/g, "");
    h += `<div class="grow"><span class="lbl">${lbl}</span><div class="gtrack">`;
    for (const s of segs[n]) h += `<div class="seg ${s.c}" style="left:${s.s / SPAN * 100}%;width:${Math.max(0.3, (s.e - s.s) / SPAN * 100)}%" title="${s.s}-${s.e} ms"></div>`;
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
    """Fill the template with the recorded events and save it."""
    verdict = ('<span class="ok">all 8 checks passed</span>' if summary["all_ok"]
               else '<span class="bad">FAILED: ' + "; ".join(c["name"] for c in summary["checks"] if not c["ok"]) + "</span>")
    text = (f"{NUM_READERS} readers, {NUM_WRITERS} writers, {ROUNDS} rounds each | {len(events)} events recorded | "
            f"max readers at once: {summary['max_readers']} | final value {summary['final_value']} "
            f"(expected {summary['expected_value']}) | {verdict}")
    checks_html = "".join(f"<li>{'PASS' if c['ok'] else 'FAIL'} - {c['name']} <i>{c['detail']}</i></li>" for c in summary["checks"])
    config = {"readers": NUM_READERS, "writers": NUM_WRITERS, "rounds": ROUNDS}
    html = (HTML_TEMPLATE
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
    threads = []
    for i in range(1, NUM_READERS + 1):
        threads.append(threading.Thread(target=reader, args=(i,), name=f"R{i}"))
    for i in range(1, NUM_WRITERS + 1):
        threads.append(threading.Thread(target=writer, args=(i,), name=f"W{i}"))
    random.shuffle(threads)             # so readers and writers don't always start in the same order

    print(f"starting {NUM_READERS} readers and {NUM_WRITERS} writers, {ROUNDS} rounds each (monitor, writer preference)\n")
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    deadline = t0 + JOIN_TIMEOUT
    for t in threads:
        t.join(max(0.0, deadline - time.perf_counter()))   # check 7: don't hang forever on a deadlock
    elapsed = time.perf_counter() - t0

    summary = check_results(threads, elapsed)
    write_html(summary, open_browser)


if __name__ == "__main__":
    main()
