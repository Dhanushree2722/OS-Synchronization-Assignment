"""
Q1 - Readers-Writers problem with semaphores

Rules I have to keep:
  - many readers can read at the same time
  - only one writer can write at a time
  - nobody reads while a writer is writing

Run it with:  python readers_writers.py
It starts the threads, prints what happens, checks the rules and writes
simulation.html next to this file (and opens it in the browser).

About fairness: the turnstile semaphore stops a stream of readers from blocking
a writer forever - once a writer is waiting, new readers queue up behind it.
I can't call it a guarantee though. Python's Semaphore doesn't promise FIFO
wake-up and a woken thread still races with threads calling acquire() at the
same time, so in theory a reader could keep getting in first. Writers also
don't get any priority over each other. So: writer starvation is avoided in
practice, not proven impossible.

Only standard library modules are used (threading, time, random, json, os, webbrowser).
"""

import json
import os
import random
import threading
import time
import webbrowser

# ------------------------------------------------------------------
# Settings. Change these during the viva and run again.
# ------------------------------------------------------------------
NUM_READERS = 5
NUM_WRITERS = 2
ROUNDS = 3                  # how many times each thread tries to enter
READ_TIME = (0.15, 0.40)    # seconds a reader stays inside (random in this range)
WRITE_TIME = (0.25, 0.50)   # seconds a writer stays inside
THINK_TIME = (0.05, 0.60)   # pause between two attempts of the same thread
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation.html")

# ------------------------------------------------------------------
# The shared resource. This is what the critical section protects.
# A very small "database": one number and who wrote it last.
# ------------------------------------------------------------------
shared_data = {"value": 0, "written_by": "nobody yet"}

# ------------------------------------------------------------------
# Synchronisation variables
# ------------------------------------------------------------------
reader_count = 0                      # readers currently inside the critical section
mutex = threading.Semaphore(1)        # protects reader_count (plain binary semaphore)
resource = threading.Semaphore(1)     # protects shared_data. Held by ONE writer, or by the whole reader group
turnstile = threading.Semaphore(1)    # fairness gate: while a writer is queued here, new readers wait behind it
                                      # (practical fairness only - see the note at the top of the file)

# ------------------------------------------------------------------
# Event recording. Every state change goes into `events`, and the
# HTML page at the end is built only from this list.
# ------------------------------------------------------------------
events = []
log_lock = threading.Lock()           # the list is shared by all threads, so it needs protection too
start_time = time.perf_counter()

# counters used only to double-check the rules while the program runs.
# `inside` counts threads that are actually reading/writing right now.
# `holder` says who owns the `resource` semaphore: "free", "readers" (the
# reader group) or "writer". These are two different things: a reader can be
# finished with its read while the group still holds the resource.
inside = {"readers": 0, "writers": 0, "max_readers": 0}
holder = {"who": "free"}
violations = []


def _append(role, pid, state, note, value):
    """Add one event. Caller must already hold log_lock."""
    t_ms = round((time.perf_counter() - start_time) * 1000)
    events.append({
        "t": t_ms,
        "role": role,
        "id": pid,
        "state": state,
        "readers_inside": inside["readers"],
        "writer_inside": inside["writers"] == 1,
        "resource": holder["who"],
        "value": value,
        "note": note,
    })
    label = ("R" if role == "reader" else "W") + str(pid)
    print(f"[{t_ms:6d} ms] {label:<3} {state:<18} resource={holder['who']:<7} {note}")


def record(role, pid, state, note="", value=None, now_holding=None):
    """Store one event and check the rules.

    now_holding="readers"/"writer" means the caller has JUST acquired `resource`
    (or joined the reader group that holds it). Releases are logged by
    release_resource(), never by record().
    """
    with log_lock:
        if now_holding == "writer":
            if holder["who"] != "free":
                violations.append(f"W{pid} took the resource while it was held by {holder['who']}")
            holder["who"] = "writer"
        elif now_holding == "readers":
            if holder["who"] == "writer":
                violations.append(f"R{pid} started reading while a writer held the resource")
            holder["who"] = "readers"

        # entry / exit bookkeeping - this is how we verify correctness
        if state == "reading":
            inside["readers"] += 1
            inside["max_readers"] = max(inside["max_readers"], inside["readers"])
            if inside["writers"] > 0:
                violations.append(f"R{pid} started reading while a writer was inside")
        elif state == "writing":
            inside["writers"] += 1
            if inside["readers"] > 0:
                violations.append(f"W{pid} started writing while {inside['readers']} reader(s) were inside")
            if inside["writers"] > 1:
                violations.append(f"W{pid} started writing while another writer was inside")
        elif state == "finished reading":
            inside["readers"] -= 1
        elif state == "finished writing":
            inside["writers"] -= 1

        _append(role, pid, state, note, value)


def release_resource(role, pid):
    """Give `resource` back AND log it, as one step.

    Both happen under log_lock, so a thread that wakes up because of this
    release cannot log its own entry before the release is in the log.
    This is the moment the shared resource really becomes available.
    """
    with log_lock:
        if holder["who"] == "free":
            violations.append(f"{role} {pid} released a resource that was already free")
        resource.release()
        holder["who"] = "free"
        _append(role, pid, "released resource", "resource is free again", None)


def reader(rid):
    """One reader thread. Runs ROUNDS times."""
    global reader_count
    for _ in range(ROUNDS):
        time.sleep(random.uniform(*THINK_TIME))      # doing something else
        record("reader", rid, "waiting")

        # if a writer is already waiting at the turnstile we queue behind it,
        # otherwise we pass straight through. Readers that got past the gate
        # before the writer took it still enter, so the writer waits only for
        # that finite group, not for every reader that keeps arriving.
        turnstile.acquire()
        turnstile.release()

        # ---- entry section: update reader_count safely ----
        mutex.acquire()
        reader_count += 1
        if reader_count == 1:          # first reader in locks the resource for the group
            resource.acquire()
        # The group holds `resource` now, so we are inside the critical section.
        # Logged while still holding mutex: the logged count equals reader_count
        # and two readers cannot log out of order.
        value = shared_data["value"]
        record("reader", rid, "reading", f"sees value {value}", value, now_holding="readers")
        mutex.release()

        # ---- critical section (reading) ----
        time.sleep(random.uniform(*READ_TIME))       # pretend the read takes a while

        # ---- exit section ----
        mutex.acquire()
        reader_count -= 1
        # This reader is done, but the resource is still held by the group
        # until the LAST reader releases it - so these are two separate events.
        record("reader", rid, "finished reading", "", value)
        if reader_count == 0:          # last reader out gives the resource back
            release_resource("reader", rid)
        mutex.release()

        record("reader", rid, "idle")


def writer(wid):
    """One writer thread. Runs ROUNDS times."""
    for _ in range(ROUNDS):
        time.sleep(random.uniform(*THINK_TIME))
        record("writer", wid, "waiting")

        turnstile.acquire()            # hold the gate so new readers line up behind us
        resource.acquire()             # wait for current readers / writer to leave
        turnstile.release()            # gate open again, we own the resource now
                                       # (whoever wakes first here - reader or another writer - is up to the
                                       #  scheduler; no priority between writers)

        # ---- critical section (writing) ----
        old = shared_data["value"]
        record("writer", wid, "writing", f"changing {old} -> {old + 1}", old, now_holding="writer")
        time.sleep(random.uniform(*WRITE_TIME))      # slow two-step update on purpose:
        shared_data["value"] = old + 1               # without the semaphores this is where
        shared_data["written_by"] = f"W{wid}"        # a lost update would show up
        record("writer", wid, "finished writing", f"value is now {old + 1}", old + 1)
        # ---- end of critical section ----

        release_resource("writer", wid)              # resource becomes available here, and is logged as such
        record("writer", wid, "idle")


def check_results():
    """Print a short verdict. Returns a dict that also goes into the HTML."""
    expected = NUM_WRITERS * ROUNDS
    actual = shared_data["value"]
    if actual != expected:
        violations.append(f"final value is {actual}, expected {expected} (lost update)")
    if holder["who"] != "free":
        violations.append(f"resource still held by {holder['who']} after all threads finished")

    print()
    print("---- checks ----")
    print(f"readers inside at the same time (max) : {inside['max_readers']}")
    print(f"final value                           : {actual} (expected {expected})")
    print(f"last written by                       : {shared_data['written_by']}")
    print(f"reading/writing overlap seen          : {'NO' if not violations else 'YES'}")
    if violations:
        for v in violations:
            print("  !!", v)
        print("RESULT: FAILED")
    else:
        print("RESULT: all rules held")
    return {
        "max_readers": inside["max_readers"],
        "final_value": actual,
        "expected_value": expected,
        "violations": violations,
        "events": len(events),
    }


# ------------------------------------------------------------------
# HTML generation. Everything the page shows comes from `events`.
# ------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Readers-Writers (semaphores) - execution replay</title>
<style>
  body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f6f9; color: #222; }
  header { background: #1f3a5f; color: #fff; padding: 14px 22px; }
  header h1 { margin: 0 0 4px; font-size: 20px; }
  header .sub { font-size: 13px; opacity: .9; }
  .ok { color: #7CFC9A; font-weight: bold; } .bad { color: #ff8a80; font-weight: bold; }
  main { padding: 16px 22px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .wide { grid-column: 1 / -1; }
  .card { background: #fff; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card h2 { margin: 0 0 10px; font-size: 15px; color: #1f3a5f; }
  .controls button, .controls select { font-size: 14px; padding: 6px 12px; margin-right: 6px; }
  .procs { display: flex; flex-wrap: wrap; gap: 8px; }
  .proc { width: 118px; border-radius: 6px; padding: 8px; border: 2px solid #ccc; background: #eee; text-align: center; transition: background .15s; }
  .proc b { display: block; font-size: 16px; }
  .proc small { display: block; font-size: 11px; min-height: 14px; color: #444; }
  .idle { background: #ececec; border-color: #ccc; }
  .wait { background: #fff3cd; border-color: #e0b400; }
  .active-r { background: #d4edda; border-color: #28a745; }
  .active-w { background: #f8d7da; border-color: #dc3545; }
  .leaving { background: #cfe2ff; border-color: #0d6efd; }
  #resource { font-size: 15px; line-height: 1.7; }
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
</style>
</head>
<body>
<header>
  <h1>Readers-Writers Problem - semaphore solution (replay of a real run)</h1>
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
      <span class="idle">idle</span><span class="wait">waiting</span><span class="active-r">reading</span><span class="active-w">writing</span><span class="leaving">finished / released</span>
    </span>
  </div>

  <div class="card"><h2>Readers</h2><div class="procs" id="readers"></div></div>
  <div class="card"><h2>Writers</h2><div class="procs" id="writers"></div></div>

  <div class="card"><h2>Shared resource (critical section)</h2><div id="resource"></div></div>
  <div class="card"><h2>Who is waiting</h2><div id="waiting">nobody</div></div>

  <div class="card wide"><h2>Timeline (RES row = who holds the resource; yellow = waiting, green = reading, red = writing)</h2>
    <div class="gantt" id="gantt"></div><div class="axis"><span>0 ms</span><span id="tmax"></span></div></div>

  <div class="card wide"><h2>Event log recorded by the program</h2><div id="log"></div></div>
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

function cls(s, role) {
  if (s === "waiting") return "wait";
  if (s === "reading") return "active-r";
  if (s === "writing") return "active-w";
  if (s.startsWith("finished") || s === "released resource") return "leaving";
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

  // Resource status = who actually holds the `resource` semaphore, exactly as
  // the program recorded it at this event (cur.resource). This is separate from
  // which processes are reading/writing: a reader can be finished while the
  // group still holds the lock, and a writer that is finished still holds it
  // until its "released resource" event.
  const readersIn = [], waiting = [];
  let writerIn = null;
  for (const k in st) {
    const s = st[k].state, lbl = (k.startsWith("reader") ? "R" : "W") + k.replace(/\D/g, "");
    if (s === "reading") readersIn.push(lbl);
    if (s === "writing" || s === "finished writing") writerIn = lbl;
    if (s === "waiting") waiting.push(lbl);
  }
  const nReaders = cur ? cur.readers_inside : 0;
  const owner = cur ? cur.resource : "free";
  let status;
  if (owner === "writer") {
    status = cur.writer_inside
      ? `<span class="busy-w">LOCKED FOR WRITING by ${writerIn}</span>`
      : `<span class="busy-w">LOCKED by ${writerIn} - write finished, not released yet</span>`;
  } else if (owner === "readers") {
    status = nReaders > 0
      ? `<span class="busy-r">LOCKED BY READER GROUP - ${readersIn.join(", ")} reading (${nReaders} at once)</span>`
      : `<span class="busy-r">LOCKED BY READER GROUP - last reader finished, not released yet</span>`;
  } else status = `<span class="free">FREE</span>`;
  document.getElementById("resource").innerHTML =
    `status: ${status}<br>value: <span class="big">${value}</span><br>last written by: ${writtenBy}` +
    `<br>readers currently reading: ${nReaders}`;
  document.getElementById("waiting").textContent = waiting.length ? waiting.join(", ") : "nobody";

  const rows = document.querySelectorAll("#log tr[data-i]");
  rows.forEach(r => { const i = +r.dataset.i; r.className = i === idx ? "cur" : (i < idx ? "done" : ""); });
  if (cur) { const r = rows[idx]; if (r) r.scrollIntoView({ block: "nearest" }); }
  document.getElementById("cursor").style.left = `calc(34px + ${cur ? (cur.t / TMAX * 100) : 0}% * (100% - 34px) / 100%)`;
}

// ---- static parts built once: event table + gantt ----
const TMAX = EVENTS.length ? EVENTS[EVENTS.length - 1].t : 1;
document.getElementById("tmax").textContent = TMAX + " ms";
(function buildLog() {
  let h = "<table><tr><th>#</th><th>time</th><th>who</th><th>state</th><th>readers reading</th><th>writer writing</th><th>resource held by</th><th>note</th></tr>";
  EVENTS.forEach((e, i) => {
    h += `<tr data-i="${i}"><td>${i + 1}</td><td>${e.t} ms</td><td>${e.role === "reader" ? "R" : "W"}${e.id}</td><td>${e.state}</td><td>${e.readers_inside}</td><td>${e.writer_inside ? "yes" : "no"}</td><td>${e.resource}</td><td>${e.note || ""}</td></tr>`;
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
    // RES row: a segment for every stretch the semaphore is held, from the recorded holder
    if (e.resource !== prevOwner) {
      if (open.resource) { segs.resource.push({ ...open.resource, e: e.t }); delete open.resource; }
      if (e.resource !== "free") open.resource = { s: e.t, c: e.resource === "readers" ? "r" : "x" };
      prevOwner = e.resource;
    }
    const k = key(e);
    if (e.state === "waiting") open[k] = { s: e.t, c: "w" };
    else if (e.state === "reading" || e.state === "writing") {
      if (open[k]) { segs[k].push({ ...open[k], e: e.t }); }
      open[k] = { s: e.t, c: e.state === "reading" ? "r" : "x" };
    } else if (e.state.startsWith("finished")) {
      if (open[k]) { segs[k].push({ ...open[k], e: e.t }); delete open[k]; }
    }
  }
  let h = "";
  for (const n of names) {
    const lbl = n === "resource" ? "RES" : (n.startsWith("reader") ? "R" : "W") + n.replace(/\D/g, "");
    h += `<div class="grow"><span class="lbl">${lbl}</span><div class="gtrack">`;
    for (const s of segs[n]) h += `<div class="seg ${s.c}" style="left:${s.s / TMAX * 100}%;width:${Math.max(0.3, (s.e - s.s) / TMAX * 100)}%" title="${s.s}-${s.e} ms"></div>`;
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


def write_html(summary):
    """Fill the template with the recorded events and save it."""
    if summary["violations"]:
        verdict = '<span class="bad">FAILED: ' + "; ".join(summary["violations"]) + "</span>"
    else:
        verdict = '<span class="ok">all checks passed - no read/write overlap, no lost update</span>'
    text = (f"{NUM_READERS} readers, {NUM_WRITERS} writers, {ROUNDS} rounds each | "
            f"{summary['events']} events recorded | max readers inside at once: {summary['max_readers']} | "
            f"final value {summary['final_value']} (expected {summary['expected_value']}) | {verdict}")
    config = {"readers": NUM_READERS, "writers": NUM_WRITERS, "rounds": ROUNDS}
    html = (HTML_TEMPLATE
            .replace("__EVENTS__", json.dumps(events))
            .replace("__CONFIG__", json.dumps(config))
            .replace("__SUMMARY__", text)
            .replace("__NEVENTS__", str(len(events))))
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML written to {HTML_FILE}")
    webbrowser.open("file:///" + HTML_FILE.replace(os.sep, "/"))


def main():
    threads = []
    for i in range(1, NUM_READERS + 1):
        threads.append(threading.Thread(target=reader, args=(i,), name=f"R{i}"))
    for i in range(1, NUM_WRITERS + 1):
        threads.append(threading.Thread(target=writer, args=(i,), name=f"W{i}"))
    random.shuffle(threads)             # so readers and writers don't always start in the same order

    print(f"starting {NUM_READERS} readers and {NUM_WRITERS} writers, {ROUNDS} rounds each\n")
    for t in threads:
        t.start()
    for t in threads:
        t.join()                        # wait until every thread is done

    summary = check_results()
    write_html(summary)


if __name__ == "__main__":
    main()
