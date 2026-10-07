---
name: next-step
description: Work the Motion AI build plan in PLAN.md. Reads the plan to decide what to do next, then starts, resumes, finishes, blocks or skips a task on its own branch, opens the pull request, and keeps PLAN.md in sync. Use this whenever the user asks what to work on next, what's next, the next step, to continue or pick up where we left off, to start the next task, or to mark a plan task started, done, blocked or skipped. Use it even for a bare "next", "keep going" or "let's continue" in this repo, and after finishing any plan task so the plan is updated and the PR opened before moving on. For a read-only overview use the roadmap skill instead.
argument-hint: "[start | done | block | skip] [task-id] [--note \"...\"]"
---

# Next step

PLAN.md at the repo root is the single source of truth for what to build and in what order. This skill turns it into the next concrete piece of work, does that work on a branch, opens the pull request, and writes back what happened so the next session starts from the truth rather than from memory.

Everything that can be done deterministically is done by two bundled scripts. Run them from the repo root:

```bash
python3 .claude/skills/next-step/scripts/plan.py next                 # what to work on (resume first, then ready tasks)
python3 .claude/skills/next-step/scripts/plan.py next --exclude M0.2  # ignore tasks that already have an open PR
python3 .claude/skills/next-step/scripts/plan.py show M1.3            # one task in full
python3 .claude/skills/next-step/scripts/plan.py set M1.3 in-progress
python3 .claude/skills/next-step/scripts/plan.py set M1.3 done --note "what proves it: tests, files, measurements"
python3 .claude/skills/next-step/scripts/plan.py set M1.3 blocked --note "waiting on <who>: <what>"
python3 .claude/skills/next-step/scripts/plan.py check                # validate ids, dependencies, cycles

.claude/skills/next-step/scripts/ghp pr list --state open             # gh, as the personal account
```

`plan.py` walks up from the current directory to find PLAN.md; pass `--plan <path>` if it cannot.

## Git and GitHub

- Remote `origin` is https://github.com/cmenguy/anim8te. `main` is protected on GitHub: nothing lands there except through a pull request, not even for the owner.
- **One task, one branch, one PR.** Branch names are `task/<id>-<few-words>`, for example `task/M0.2-fal-smoke-test`. Commit messages and the PR title start with the task id: `M0.2: add fal smoke-test script`.
- This machine has two GitHub logins in `gh`, and the active one is usually the work account. The repo's local git config already carries the personal identity (`cmenguy`, menguy.charles@gmail.com) and a credential helper that pushes with the personal token, so plain `git push` is fine. `gh` has no per-repo setting, so **never run bare `gh` here**; use the wrapper `.claude/skills/next-step/scripts/ghp`, which runs `gh` as `cmenguy`.
- The plan's status change is part of the task's PR. Until the PR merges, `main` still says `todo` for that task. That is why step 1 scans open PRs.
- Opening a PR is the end of a task from this skill's side. Merging is the owner's call: report the link and stop. If the user says to merge, use `ghp pr merge <n> --squash --delete-branch`.

## Arguments

`$ARGUMENTS` may be empty or one of these shapes:

| Invocation | Meaning |
|---|---|
| `/next-step` | Pick the next task and present it. Ask whether to start it. |
| `/next-step start` | Pick the next task and start working on it right away. |
| `/next-step start M2.4` | Start a specific task (even if it is not the top pick; warn if its dependencies are unfinished). |
| `/next-step done M2.4 --note "..."` | Verify the task's Done when, mark it done, push, open the PR. |
| `/next-step block M2.4 --note "..."` | Mark it blocked, push what exists as a draft PR, say what unblocks it. |
| `/next-step skip M2.4 --note "..."` | Mark it skipped. Only on the user's say-so. |

## Workflow

### 1. Read the plan state

Start from an up-to-date `main` unless you are resuming a task branch:

```bash
git status --short --branch
git checkout main && git pull --ff-only
.claude/skills/next-step/scripts/ghp pr list --state open --json number,title,headRefName,isDraft,url
```

Pull the task ids out of the open PR titles and branch names, then run `plan.py next --exclude <ids>` and `plan.py check`. Tasks with an open PR are in review (or blocked, if the PR is a draft); mention them in one line each with the link, and do not pick them again. If `check` prints errors or warnings, mention them in one line too, because a broken dependency graph makes the pick wrong.

The `next` output has up to two parts: **RESUME** (tasks already in progress) and **READY TO START** (todo tasks whose dependencies are all done, in milestone order, optional tasks last). Blocked tasks are never suggested.

### 2. Choose the candidate

- An in-progress task wins by default. Someone started it; finishing it beats starting something new. Only pass over it if the user names another task or says it is parked. Its branch is `task/<id>-...`; check it out and continue there.
- Otherwise take the top ready task. When several are ready, they are parallel-able by construction; say so in one line so the user can pick a different track (for example Godot setup while the pipeline waits on an account).
- A task the user names explicitly always wins, with a warning if `show` lists unfinished dependencies.

### 3. Gather the context the task needs

Run `plan.py show <id>` for the full block. Then:

- Read the GDD sections the Notes cite (`grep -n "^## 4" GDD.md` style lookups; the plan cites them as "GDD §4 stage 5" or "§7.1 Flow B").
- Check the repo for what already exists. If the task's Done when is partly or fully met on disk, the plan is stale; say so and offer to mark it done or narrow it, rather than redoing the work.
- Look at the task's **Needs decision** line. Those are rows from the Decisions table in PLAN.md that this task cannot finish without. A `proposed` decision has a default written in; an `open` one does not.

### 4. Present the task

Keep this short; the user wants to start, not read a report. Give:

- The task id and title, and why it is next in one clause (resume, or first ready in milestone order).
- The Done when, as the checklist the work will be judged against.
- Anything only the user can do: account sign-ups, license acceptance, paying for a GPU box, picking a decision. Name the exact site or action.
- Decisions it needs. For each one, state a recommendation and the trade-off in a sentence, then ask for the call. Do not decide `open` questions silently; `proposed` ones can proceed on the written default if the user is fine with it.

With no `start` argument, end by asking whether to start. With `start`, go straight to step 5.

### 5. Do the work

1. Branch and record the start, so an interrupted session still shows what was underway:

   ```bash
   git checkout -b task/<id>-<few-words>
   python3 .claude/skills/next-step/scripts/plan.py set <id> in-progress
   git add PLAN.md && git commit -m "<id>: start"
   ```

2. Work to the Done when, and only to it. The plan already decided the scope; neighbouring tasks exist for the things that look tempting to do "while you're here". If something outside the task turns out to be necessary, say so and either add a task (keeping the field format) or note it in the Notes line.
3. Commit in small steps with `<id>:` prefixes. Never commit `.env`, anything under `library/`, or checkpoints; `.gitignore` covers them, keep it that way.
4. Use the matching tool for the job: the `claude-api` skill for anything calling Anthropic models (M3.18), the Godot docs for engine questions, the GDD's install snippets for GVHMR and fal.
5. When the user must act (create a key, accept a license, approve spend), stop at that point, say exactly what to do and where, and mark the task blocked with `--note "waiting on owner: <what>"`. Commit, push, and open a **draft** PR so the partial work is visible (`ghp pr create --draft ...`). Then go back to `main` and pick the next ready task if there is one that does not depend on it.
6. If a decision is recorded during the task, update the Decisions table row by hand: set the Status cell to `decided` and write the decision in the Decision cell. The script reads that table but does not edit it.

### 6. Finish the task

Walk through every clause of the Done when against the repo: run the tests it names, open the files it names, check the numbers it asks for. Then:

```bash
python3 .claude/skills/next-step/scripts/plan.py set <id> done --note "<the evidence, one line>"
git add -A && git commit -m "<id>: done"
git push -u origin HEAD
.claude/skills/next-step/scripts/ghp pr create --base main --title "<id>: <task title>" --body-file <body.md>
```

The note matters. "tests pass, GLB imports with 22/22 bones mapped" tells the next session more than "done". Write the PR body to a scratch file with this shape:

```markdown
## <id>: <task title>

**Done when:** <copied from the plan>

**Evidence**
- <what was run, what it showed, files to look at>

**Plan changes**
- <id>: todo -> done
- <decisions recorded, tasks added or edited, if any>
```

Gate tasks (`Gate: yes`, currently M0.9 go/no-go) are the exception: prepare the evidence, present it, and let the owner make the call. Never mark a gate done on your own judgement.

Report the PR link, then switch back to `main` (`git checkout main`) and run step 1 again to tell the user in one or two lines what comes next. Do not merge.

### 7. Blocked and skipped

- `blocked` always carries a note saying who or what unblocks it, and its branch has a draft PR. When the blocker clears, check the branch out, set the task back to `in-progress`, and continue; mark the PR ready with `ghp pr ready <n>` when it is done.
- `skipped` is for tasks the user has decided not to do (usually `Optional: yes` ones). It counts as finished for dependency purposes, so downstream tasks become ready. Say that when skipping something a later task relies on. A skip is a one-line PLAN.md change; it still goes through a small PR.

## Editing the plan itself

The plan is meant to change as the project teaches us things. Editing by hand is fine for titles, notes, dependencies, effort, and for adding or splitting tasks. Keep the exact shape the parser expects:

```markdown
### M2.12 Title in sentence case
- **Status:** todo
- **Depends on:** M2.6, M2.7
- **Component:** godot
- **Effort:** M
- **Done when:** a concrete check someone else could verify.
- **Notes:** why this task exists, GDD section, pointers.
```

New task ids continue the milestone's numbering. Always run `plan.py check` after a hand edit; it catches unknown dependencies, cycles and missing Done when lines. Plan edits made during a task ride along in that task's PR; a standalone plan edit gets its own small PR.

Do not renumber existing tasks: the log lines, branch names and the Decisions table refer to them.

## Example

User: `/next-step`

No open PRs. Script says M0.2 is ready and needs nothing decided. The reply looks like:

> **Next: M0.2 fal account, API key and first H3 Max smoke test** (first ready task in M0; M0.1 is done).
>
> Done when: `FAL_KEY` in `.env`, one 5 s 768P image-to-video clip generated from a full-body image with the fal client, mp4 saved, real cost noted.
>
> You need to create the key at https://fal.ai/dashboard/keys and put it in `.env`; I can do the rest. Start it?

User says yes: branch `task/M0.2-fal-smoke-test`, mark in-progress and commit, write the smoke-test script under `docs/scratch/`, run it once the key exists, record the cost in the task's Notes, mark done with the cost as the note, push, open the PR, report the link, and say that M0.4 is next (it needs Q3 decided).
