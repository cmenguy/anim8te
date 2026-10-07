---
name: roadmap
description: Summarise the Motion AI roadmap and progress from PLAN.md, including milestone status, percent done, what is in flight, what is blocked, the go/no-go gate, decisions that need making and what comes next. Use this whenever the user asks for the roadmap, status, progress, "where are we", "how far along are we", a milestone overview, what is left in a milestone, or a short summary to share with someone else. Read-only, it never edits PLAN.md; use the next-step skill to pick, start or finish tasks.
argument-hint: "[milestone id such as M2]"
---

# Roadmap

A read-only view of PLAN.md, the Motion AI build plan. The numbers come from the plan file, not from guesswork, so the summary is only as current as the plan. If the repo clearly disagrees with the plan (files exist for a task marked todo, say), point that out as "plan may be stale" and suggest reconciling with the next-step skill; do not silently correct the numbers.

The parser lives with the next-step skill so there is one copy of it. Run from the repo root:

```bash
git checkout main && git pull --ff-only                                   # status lives on main
python3 .claude/skills/next-step/scripts/plan.py summary                  # whole plan
python3 .claude/skills/next-step/scripts/plan.py summary M2               # one milestone, task by task
python3 .claude/skills/next-step/scripts/plan.py check                    # integrity (only report problems)
python3 .claude/skills/next-step/scripts/plan.py summary --json           # if you need to compute something
gh pr list --state open --json number,title,headRefName,isDraft,url
```

Every task is done on its own branch and lands on `main` through a pull request (remote: https://github.com/cmenguy/anim8te), and the task's status change rides in that PR. So `main` lags the open PRs: a task with an open PR is finished but not merged (or blocked, if the PR is a draft). List open PRs with `gh` and show them as **In review**. `gh` needs the personal token: `.envrc` exports `GH_TOKEN` for the terminal, but not for this tool's shell, so if `echo ${GH_TOKEN:+set}` prints nothing, prefix the command with `GH_TOKEN=$(gh auth token --hostname github.com --user cmenguy)`. If you are not on `main`, say which branch the numbers come from.

## What to produce

### Whole-plan summary (no argument)

Run `summary` and `check`. Then write the summary in this shape, trimming any section that is empty:

```
**Motion AI roadmap, <today>**: <done>/<total> tasks done (<pct>%). Current milestone: <id> <title> (<done>/<total>). Gate <id>: passed | pending.

| Milestone | Status | Done | Title |
|---|---|---|---|
| M0 | in-progress | 3/9 | Accounts, GPU box, feasibility test |
...

**In review:** <id> <title>, PR #<n> <url> (draft = blocked)
**In flight:** <id> <title> (last log line if any)
**Blocked:** <id> <title>: <what unblocks it, from the log>
**Up next:** the first two or three ready tasks, one line each, with effort
**Decisions needed now:** the "needed now" rows from the script, each with the proposed default if there is one
**Watch:** one or two risks from GDD §11 that bite in the current milestone, one line each
```

Keep it to roughly twenty lines. The user asked for a summary, not the plan read back. Do not list every task.

### Milestone drill-down (argument such as `M2`)

Run `summary <id>`. Report the milestone's Done when, then its tasks in order with status, effort, flags (optional, gate) and, for todo tasks, what each one waits on. Close with the milestone's blockers and which of its tasks are ready today.

### Questions rather than reports

The user may ask something narrower: "how much of M3 is left", "what is blocked", "when do we need to decide Q4", "what did we finish this week". Answer that question from the script output (the log lines carry dates) instead of pasting the whole template.

## Reading the script output

- A milestone is `done` when all its tasks are done or skipped, `in-progress` when any task is done or in progress, else `todo`.
- Percent done excludes skipped tasks.
- "Ready to start" means every dependency is finished; those tasks are parallel-able.
- "Decisions needed now" are open rows of the plan's Decisions table whose task is ready, in progress, or in the current milestone. `proposed` rows have a default written in; `open` rows do not.
- Gates (currently M0.9, the go/no-go on GVHMR quality) decide whether later milestones happen at all; say plainly when the gate is still pending.

## What not to do

- Do not change PLAN.md. Status updates, notes and decisions go through the next-step skill, which also writes the dated log lines and opens the PR.
- Do not merge, close or edit pull requests. Listing them is all this skill does with GitHub.
- Do not estimate dates or velocity unless asked; the plan carries S/M/L effort, not a calendar. If asked, add up effort for the remaining tasks and say that it assumes an AI coding agent does most of the typing (S under half a day, M one to two days, L three or more).
- Do not pad with restated GDD content. Link the section instead.
