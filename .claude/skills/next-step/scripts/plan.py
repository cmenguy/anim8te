#!/usr/bin/env python3
"""Read and update PLAN.md, the Motion AI build plan.

The plan is plain Markdown with a fixed shape so this script can parse it:

    ## M1: Milestone title                 <- milestone
    **Done when:** ...                     <- milestone-level field
    **Gate:** ...                          <- optional

    ### M1.3 Task title                    <- task
    - **Status:** todo                     <- todo | in-progress | done | blocked | skipped
    - **Depends on:** M1.1, M0.2           <- or "none"
    - **Component:** pipeline
    - **Effort:** M                        <- S | M | L
    - **Optional:** yes                    <- optional line
    - **Done when:** ...
    - **Notes:** ...
    - **Log:** 2026-10-06 ...              <- appended by `set`, zero or more

    ## Decisions                           <- table with | ID | Question | Status | Decision | Needed by |

Commands:
    plan.py summary [MILESTONE] [--json]   progress per milestone, in-flight, blocked, open decisions
    plan.py next [--all] [--json] [--exclude M1.2,M1.3]
                                           what to work on next (in-progress first, then ready tasks);
                                           --exclude lists tasks that already have an open PR
    plan.py show ID                        print one task block
    plan.py list [--status S] [--milestone M]
    plan.py set ID STATUS [--note TEXT]    update a task's status and append a dated log line
    plan.py check                          validate ids, dependencies, cycles, statuses

Use --plan PATH to point at a different plan file. By default the script walks
up from the current directory until it finds PLAN.md.
"""

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import OrderedDict

STATUSES = ["todo", "in-progress", "done", "blocked", "skipped"]
FINISHED = {"done", "skipped"}

MILESTONE_RE = re.compile(r"^## (M\d+): (.+?)\s*$")
TASK_RE = re.compile(r"^### (M\d+\.\d+) (.+?)\s*$")
FIELD_RE = re.compile(r"^- \*\*([A-Za-z ]+):\*\* ?(.*?)\s*$")
MFIELD_RE = re.compile(r"^\*\*([A-Za-z ]+):\*\* ?(.*?)\s*$")
SECTION_RE = re.compile(r"^## (.+?)\s*$")
TASK_ID_RE = re.compile(r"M\d+\.\d+")


# --------------------------------------------------------------------------- parsing

def find_plan(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get("ANIM8TE_PLAN")
    if env:
        return env
    here = os.path.abspath(os.getcwd())
    while True:
        cand = os.path.join(here, "PLAN.md")
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    sys.exit("PLAN.md not found (walked up from the current directory). Use --plan PATH.")


def parse_deps(text):
    text = text.strip()
    if not text or text.lower() in {"none", "-", "—", "–"}:
        return []
    return TASK_ID_RE.findall(text)


def id_key(task_id):
    m, t = task_id[1:].split(".")
    return (int(m), int(t))


def parse_plan(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    milestones = OrderedDict()
    tasks = OrderedDict()
    decisions = []
    cur_ms = None
    cur_task = None
    section = None

    for i, line in enumerate(lines):
        m = MILESTONE_RE.match(line)
        if m:
            cur_ms = m.group(1)
            cur_task = None
            section = "milestone"
            milestones[cur_ms] = {
                "id": cur_ms, "title": m.group(2), "line": i,
                "done_when": "", "gate": "", "tasks": [],
            }
            continue

        s = SECTION_RE.match(line)
        if s:
            cur_ms = None
            cur_task = None
            section = s.group(1).strip().lower()
            continue

        t = TASK_RE.match(line)
        if t:
            tid = t.group(1)
            if cur_ms is None:
                sys.exit(f"line {i+1}: task {tid} appears outside a milestone section")
            cur_task = {
                "id": tid, "title": t.group(2), "milestone": cur_ms, "line": i,
                "status": "todo", "status_line": None, "depends": [], "component": "",
                "effort": "", "optional": False, "gate": False, "done_when": "",
                "notes": "", "log": [], "last_field_line": i,
            }
            tasks[tid] = cur_task
            milestones[cur_ms]["tasks"].append(tid)
            continue

        if cur_task is not None:
            f = FIELD_RE.match(line)
            if f:
                key, val = f.group(1).strip().lower(), f.group(2).strip()
                cur_task["last_field_line"] = i
                if key == "status":
                    cur_task["status"] = val.lower()
                    cur_task["status_line"] = i
                elif key == "depends on":
                    cur_task["depends"] = parse_deps(val)
                elif key == "component":
                    cur_task["component"] = val
                elif key == "effort":
                    cur_task["effort"] = val
                elif key == "optional":
                    cur_task["optional"] = val.lower().startswith("y")
                elif key == "gate":
                    cur_task["gate"] = val.lower().startswith("y")
                elif key == "done when":
                    cur_task["done_when"] = val
                elif key == "notes":
                    cur_task["notes"] = val
                elif key == "log":
                    cur_task["log"].append(val)
                continue
            if line.strip() == "":
                # a blank line ends the field block but we keep cur_task so that
                # free-form paragraphs under a task are tolerated
                continue

        if cur_ms is not None and cur_task is None:
            mf = MFIELD_RE.match(line)
            if mf:
                key, val = mf.group(1).strip().lower(), mf.group(2).strip()
                if key == "done when":
                    milestones[cur_ms]["done_when"] = val
                elif key == "gate":
                    milestones[cur_ms]["gate"] = val
            continue

        if section == "decisions" and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 5 and re.match(r"^[QG]\d+$", cells[0]):
                decisions.append({
                    "id": cells[0], "question": cells[1], "status": cells[2].lower(),
                    "decision": cells[3], "needed_by": cells[4], "line": i,
                })

    return {"path": path, "lines": lines, "milestones": milestones, "tasks": tasks, "decisions": decisions}


# --------------------------------------------------------------------------- derived state

def milestone_status(plan, ms_id):
    ids = plan["milestones"][ms_id]["tasks"]
    if not ids:
        return "todo"
    statuses = [plan["tasks"][t]["status"] for t in ids]
    if all(s in FINISHED for s in statuses):
        return "done"
    if any(s in {"done", "in-progress"} for s in statuses):
        return "in-progress"
    return "todo"


def milestone_counts(plan, ms_id):
    ids = plan["milestones"][ms_id]["tasks"]
    c = {s: 0 for s in STATUSES}
    for t in ids:
        c[plan["tasks"][t]["status"]] += 1
    c["total"] = len(ids)
    c["countable"] = len(ids) - c["skipped"]
    return c


def unmet_deps(plan, task):
    return [d for d in task["depends"] if d not in plan["tasks"] or plan["tasks"][d]["status"] not in FINISHED]


def is_ready(plan, task):
    return task["status"] == "todo" and not unmet_deps(plan, task)


def current_milestone(plan):
    for ms_id in plan["milestones"]:
        if milestone_status(plan, ms_id) != "done":
            return ms_id
    return None


def ready_tasks(plan):
    ready = [t for t in plan["tasks"].values() if is_ready(plan, t)]
    ready.sort(key=lambda t: (t["optional"], id_key(t["id"])))
    return ready


def decisions_for(plan, task_id):
    """Open or proposed decisions whose 'Needed by' names this task."""
    return [d for d in plan["decisions"]
            if d["status"] not in {"decided", "closed"} and task_id in TASK_ID_RE.findall(d["needed_by"])]


def decisions_due(plan):
    """Open decisions whose 'Needed by' task is ready, in progress, or in the current milestone."""
    cur = current_milestone(plan)
    due = []
    for d in plan["decisions"]:
        if d["status"] in {"decided", "closed"}:
            continue
        for tid in TASK_ID_RE.findall(d["needed_by"]):
            t = plan["tasks"].get(tid)
            if t and (t["status"] == "in-progress" or is_ready(plan, t) or t["milestone"] == cur):
                due.append(d)
                break
    return due


def gate_state(plan):
    """Return list of (task, passed?) for every gate task."""
    return [(t, t["status"] == "done") for t in plan["tasks"].values() if t["gate"]]


# --------------------------------------------------------------------------- output helpers

def fmt_task_block(plan, task, with_deps_state=True):
    out = [f"### {task['id']} {task['title']}  [{task['milestone']}: {plan['milestones'][task['milestone']]['title']}]"]
    out.append(f"- Status: {task['status']}" + ("  (OPTIONAL)" if task["optional"] else "") + ("  (GATE)" if task["gate"] else ""))
    if task["depends"]:
        if with_deps_state:
            parts = []
            for d in task["depends"]:
                st = plan["tasks"][d]["status"] if d in plan["tasks"] else "unknown"
                parts.append(f"{d} [{st}]")
            out.append("- Depends on: " + ", ".join(parts))
        else:
            out.append("- Depends on: " + ", ".join(task["depends"]))
    else:
        out.append("- Depends on: none")
    if task["component"]:
        out.append(f"- Component: {task['component']}")
    if task["effort"]:
        out.append(f"- Effort: {task['effort']}")
    if task["done_when"]:
        out.append(f"- Done when: {task['done_when']}")
    if task["notes"]:
        out.append(f"- Notes: {task['notes']}")
    for entry in task["log"]:
        out.append(f"- Log: {entry}")
    for d in decisions_for(plan, task["id"]):
        tail = f" (proposed: {d['decision']})" if d["status"] == "proposed" and d["decision"] else ""
        out.append(f"- Needs decision: {d['id']} {d['question']}{tail}")
    return "\n".join(out)


def task_json(plan, task):
    d = {k: v for k, v in task.items() if k not in {"line", "status_line", "last_field_line"}}
    d["unmet_deps"] = unmet_deps(plan, task)
    return d


# --------------------------------------------------------------------------- commands

def cmd_summary(plan, args):
    tasks = plan["tasks"]
    total = len(tasks)
    counts = {s: sum(1 for t in tasks.values() if t["status"] == s) for s in STATUSES}
    countable = total - counts["skipped"]
    pct = round(100 * counts["done"] / countable) if countable else 0
    cur = current_milestone(plan)

    if args.json:
        data = {
            "totals": {**counts, "total": total, "percent_done": pct},
            "current_milestone": cur,
            "milestones": [],
            "in_progress": [task_json(plan, t) for t in tasks.values() if t["status"] == "in-progress"],
            "blocked": [task_json(plan, t) for t in tasks.values() if t["status"] == "blocked"],
            "ready": [task_json(plan, t) for t in ready_tasks(plan)],
            "gates": [{"id": t["id"], "title": t["title"], "passed": ok} for t, ok in gate_state(plan)],
            "open_decisions": [d for d in plan["decisions"] if d["status"] not in {"decided", "closed"}],
            "decisions_due": decisions_due(plan),
        }
        for ms_id, ms in plan["milestones"].items():
            c = milestone_counts(plan, ms_id)
            entry = {"id": ms_id, "title": ms["title"], "status": milestone_status(plan, ms_id),
                     "counts": c, "done_when": ms["done_when"], "gate": ms["gate"]}
            if args.milestone and args.milestone == ms_id:
                entry["tasks"] = [task_json(plan, tasks[t]) for t in ms["tasks"]]
            data["milestones"].append(entry)
        print(json.dumps(data, indent=2))
        return

    if args.milestone:
        ms_id = args.milestone.upper()
        if ms_id not in plan["milestones"]:
            sys.exit(f"unknown milestone {ms_id}; known: {', '.join(plan['milestones'])}")
        ms = plan["milestones"][ms_id]
        c = milestone_counts(plan, ms_id)
        print(f"{ms_id}: {ms['title']}  [{milestone_status(plan, ms_id)}]  {c['done']}/{c['countable']} done")
        if ms["done_when"]:
            print(f"Done when: {ms['done_when']}")
        if ms["gate"]:
            print(f"Gate: {ms['gate']}")
        print()
        for tid in ms["tasks"]:
            t = tasks[tid]
            flags = []
            if t["optional"]:
                flags.append("optional")
            if t["gate"]:
                flags.append("gate")
            um = unmet_deps(plan, t)
            dep_note = ""
            if t["status"] == "todo" and um:
                dep_note = f"  waits on {', '.join(um)}"
            elif t["status"] == "todo":
                dep_note = "  READY"
            flag_note = f"  ({', '.join(flags)})" if flags else ""
            print(f"  {tid:<6} {t['status']:<12} {t['effort'] or '-':<2} {t['title']}{flag_note}{dep_note}")
            if t["status"] in {"blocked", "in-progress"} and t["log"]:
                print(f"         last log: {t['log'][-1]}")
        return

    print(f"Motion AI plan: {total} tasks, {counts['done']} done ({pct}%), "
          f"{counts['in-progress']} in progress, {counts['blocked']} blocked, {counts['skipped']} skipped")
    if cur:
        c = milestone_counts(plan, cur)
        print(f"Current milestone: {cur} {plan['milestones'][cur]['title']} ({c['done']}/{c['countable']} done)")
    else:
        print("All milestones complete.")
    gates = gate_state(plan)
    if gates:
        print("Gates: " + "; ".join(f"{t['id']} {t['title']}: {'passed' if ok else 'pending'}" for t, ok in gates))
    print()
    print(f"{'Milestone':<10} {'Status':<12} {'Done':>7}  Title")
    for ms_id, ms in plan["milestones"].items():
        c = milestone_counts(plan, ms_id)
        marker = " <-" if ms_id == cur else ""
        print(f"{ms_id:<10} {milestone_status(plan, ms_id):<12} {c['done']:>3}/{c['countable']:<3}  {ms['title']}{marker}")
    print()

    inprog = [t for t in tasks.values() if t["status"] == "in-progress"]
    blocked = [t for t in tasks.values() if t["status"] == "blocked"]
    ready = ready_tasks(plan)
    if inprog:
        print("In progress:")
        for t in inprog:
            print(f"  {t['id']:<6} {t['title']}" + (f"  (last log: {t['log'][-1]})" if t["log"] else ""))
    if blocked:
        print("Blocked:")
        for t in blocked:
            print(f"  {t['id']:<6} {t['title']}" + (f"  (last log: {t['log'][-1]})" if t["log"] else ""))
    if ready:
        print("Ready to start (all dependencies done):")
        for t in ready[:8]:
            opt = "  (optional)" if t["optional"] else ""
            print(f"  {t['id']:<6} {t['effort'] or '-':<2} {t['title']}{opt}")
        if len(ready) > 8:
            print(f"  ... and {len(ready) - 8} more (plan.py next --all)")
    open_dec = [d for d in plan["decisions"] if d["status"] not in {"decided", "closed"}]
    due = decisions_due(plan)
    if due:
        print("Decisions needed now (their task is ready, in progress, or in the current milestone):")
        for d in due:
            tail = f"  [proposed: {d['decision']}]" if d["status"] == "proposed" and d["decision"] else ""
            print(f"  {d['id']:<4} needed by {d['needed_by']:<8} {d['question']}{tail}")
    later = [d for d in open_dec if d not in due]
    if later:
        print("Open decisions for later:")
        for d in later:
            print(f"  {d['id']:<4} needed by {d['needed_by']:<8} {d['question']}")


def cmd_next(plan, args):
    tasks = plan["tasks"]
    # Tasks with an open pull request live on a branch; main still says todo or
    # in-progress for them. The caller passes their ids so they are not picked again.
    excluded = {x.strip().upper() for x in (args.exclude or "").split(",") if x.strip()}
    inprog = [t for t in tasks.values() if t["status"] == "in-progress" and t["id"] not in excluded]
    ready = [t for t in ready_tasks(plan) if t["id"] not in excluded]
    if excluded and not args.json:
        known = [x for x in sorted(excluded, key=lambda i: id_key(i) if TASK_ID_RE.fullmatch(i) else (99, 0)) if x in tasks]
        if known:
            print("IN REVIEW (open pull request, not picked): " + ", ".join(f"{x} {tasks[x]['title']}" for x in known))
            print()

    if args.json:
        print(json.dumps({
            "in_progress": [task_json(plan, t) for t in inprog],
            "ready": [task_json(plan, t) for t in ready],
            "blocked": [task_json(plan, t) for t in tasks.values() if t["status"] == "blocked"],
            "excluded": sorted(x for x in excluded if x in tasks),
        }, indent=2))
        return

    if inprog:
        print("RESUME (already in progress):")
        for t in inprog:
            print()
            print(fmt_task_block(plan, t))
        print()

    if not ready:
        print("No task is ready to start." + ("" if inprog else " Nothing is in progress either."))
        blocked = [t for t in tasks.values() if t["status"] == "blocked"]
        waiting = [t for t in tasks.values() if t["status"] == "todo"]
        waiting.sort(key=lambda t: id_key(t["id"]))
        if blocked:
            print("Blocked tasks:")
            for t in blocked:
                print(f"  {t['id']:<6} {t['title']}" + (f"  (last log: {t['log'][-1]})" if t["log"] else ""))
        if waiting:
            print("Nearest todo tasks and what they wait on:")
            for t in waiting[:5]:
                print(f"  {t['id']:<6} {t['title']}  waits on {', '.join(unmet_deps(plan, t))}")
        return

    shown = ready if args.all else ready[:1]
    label = "READY TO START" if not inprog else "ALSO READY TO START"
    print(f"{label} ({len(ready)} task{'s' if len(ready) != 1 else ''} ready; showing {len(shown)}):")
    for t in shown:
        print()
        print(fmt_task_block(plan, t))
        # why it is next
        ms = plan["milestones"][t["milestone"]]
        reason = f"first ready task in milestone order; {t['milestone']} is " + (
            "the current milestone" if t["milestone"] == current_milestone(plan) else "ahead of the current milestone")
        if t["optional"]:
            reason += "; optional, so listed after required work"
        print(f"- Why: {reason}")
    if not args.all and len(ready) > 1:
        print()
        print("Other ready tasks (parallel-able):")
        for t in ready[1:6]:
            opt = "  (optional)" if t["optional"] else ""
            print(f"  {t['id']:<6} {t['effort'] or '-':<2} {t['title']}{opt}")
        if len(ready) > 6:
            print(f"  ... and {len(ready) - 6} more (plan.py next --all)")


def cmd_show(plan, args):
    tid = args.id.upper()
    if tid not in plan["tasks"]:
        sys.exit(f"unknown task {tid}")
    print(fmt_task_block(plan, plan["tasks"][tid]))


def cmd_list(plan, args):
    for t in plan["tasks"].values():
        if args.status and t["status"] != args.status:
            continue
        if args.milestone and t["milestone"] != args.milestone.upper():
            continue
        opt = " (optional)" if t["optional"] else ""
        print(f"{t['id']:<6} {t['status']:<12} {t['effort'] or '-':<2} {t['milestone']:<3} {t['title']}{opt}")


def cmd_set(plan, args):
    tid = args.id.upper()
    status = args.status.lower()
    if tid not in plan["tasks"]:
        sys.exit(f"unknown task {tid}")
    if status not in STATUSES:
        sys.exit(f"invalid status {status!r}; use one of {', '.join(STATUSES)}")
    task = plan["tasks"][tid]
    if task["status_line"] is None:
        sys.exit(f"{tid} has no '- **Status:**' line to update")
    warnings = []
    if status in {"in-progress", "done"}:
        um = unmet_deps(plan, task)
        if um:
            warnings.append(f"{tid} depends on unfinished task(s): {', '.join(um)}")
    if task["gate"] and status == "done" and not args.note:
        warnings.append(f"{tid} is a gate; record the decision with --note so the plan carries the evidence")

    lines = plan["lines"]
    old = task["status"]
    lines[task["status_line"]] = f"- **Status:** {status}"
    today = _dt.date.today().isoformat()
    entry = f"{today} {old} -> {status}" + (f": {args.note}" if args.note else "")
    insert_at = task["last_field_line"] + 1
    lines.insert(insert_at, f"- **Log:** {entry}")
    with open(plan["path"], "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"{tid}: {old} -> {status}")
    for w in warnings:
        print(f"warning: {w}")


def cmd_check(plan, args):
    errors, warns = [], []
    tasks = plan["tasks"]
    for t in tasks.values():
        if t["status"] not in STATUSES:
            errors.append(f"{t['id']}: invalid status {t['status']!r}")
        if not t["done_when"]:
            warns.append(f"{t['id']}: no 'Done when' criterion")
        for d in t["depends"]:
            if d == t["id"]:
                errors.append(f"{t['id']}: depends on itself")
            elif d not in tasks:
                errors.append(f"{t['id']}: depends on unknown task {d}")
            elif id_key(d) > id_key(t["id"]):
                warns.append(f"{t['id']}: depends on a later task {d} (fine if intentional)")
        if t["status"] == "done":
            um = [d for d in t["depends"] if d in tasks and tasks[d]["status"] not in FINISHED]
            if um:
                warns.append(f"{t['id']} is done but depends on unfinished {', '.join(um)}")
    # cycles
    state = {}
    def visit(tid, stack):
        state[tid] = "visiting"
        for d in tasks[tid]["depends"]:
            if d not in tasks:
                continue
            if state.get(d) == "visiting":
                errors.append("dependency cycle: " + " -> ".join(stack + [tid, d]))
            elif d not in state:
                visit(d, stack + [tid])
        state[tid] = "done"
    for tid in tasks:
        if tid not in state:
            visit(tid, [])
    for ms_id, ms in plan["milestones"].items():
        if not ms["done_when"]:
            warns.append(f"{ms_id}: no milestone-level 'Done when'")
    for d in plan["decisions"]:
        if d["status"] not in {"open", "proposed", "decided", "closed"}:
            warns.append(f"{d['id']}: unusual decision status {d['status']!r}")
    for e in errors:
        print(f"ERROR   {e}")
    for w in warns:
        print(f"warning {w}")
    print(f"{len(tasks)} tasks in {len(plan['milestones'])} milestones, {len(plan['decisions'])} decisions; "
          f"{len(errors)} errors, {len(warns)} warnings")
    if errors:
        sys.exit(1)


# --------------------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", help="path to PLAN.md (default: search upward from cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("summary"); s.add_argument("milestone", nargs="?"); s.add_argument("--json", action="store_true")
    n = sub.add_parser("next"); n.add_argument("--all", action="store_true"); n.add_argument("--json", action="store_true")
    n.add_argument("--exclude", help="comma-separated task ids with an open PR; they are listed as in review and not picked")
    sh = sub.add_parser("show"); sh.add_argument("id")
    ls = sub.add_parser("list"); ls.add_argument("--status", choices=STATUSES); ls.add_argument("--milestone")
    st = sub.add_parser("set"); st.add_argument("id"); st.add_argument("status"); st.add_argument("--note")
    sub.add_parser("check")

    args = p.parse_args(argv)
    plan = parse_plan(find_plan(args.plan))
    {"summary": cmd_summary, "next": cmd_next, "show": cmd_show, "list": cmd_list,
     "set": cmd_set, "check": cmd_check}[args.cmd](plan, args)


if __name__ == "__main__":
    main()
