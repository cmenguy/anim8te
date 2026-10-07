# Motion AI

A tool-first prototype: an AI pipeline that turns one base image plus a text prompt into game-ready humanoid animations (glTF on a canonical skeleton), a Godot "gym" to inspect them, and a workflow UI that runs the pipeline in a few clicks. The game itself is out of scope.

## Read these first

- `GDD.md`: what we are building and why. Pipeline stages, Gym, Workflow Manager, architecture, licensing, risks.
- `PLAN.md`: what to do in what order, with per-task status. The only place task status lives.
- `README.md`: human-facing overview, prerequisites, layout.

## Working the plan

- `/next-step` picks the next task from PLAN.md, marks it in progress, does the work, and marks it done with an evidence note once its "Done when" is met. Use it at the start of a session and after finishing a task.
- `/roadmap` summarises progress. Read-only.
- Both use `.claude/skills/next-step/scripts/plan.py`. Run `plan.py check` after editing PLAN.md by hand, and keep the `- **Field:** value` lines in the shape the parser expects.
- Stay inside the task's scope. Neighbouring work has its own task; add a task if something is missing rather than widening the current one.
- Gate tasks (M0.9, the go/no-go on GVHMR quality) are the owner's call. Prepare the evidence; do not mark them done.
- The Decisions table in PLAN.md holds open questions. When one is settled, set its row to `decided` and write the decision in the row.
- Milestone-level "Done when" lines say what each milestone has to prove; end-of-milestone tasks save a capture under `docs/captures/`.

## Git and GitHub

- Remote `origin`: https://github.com/cmenguy/anim8te. `main` is protected; everything lands through a pull request, including plan status changes and one-line doc fixes.
- One task, one branch, one PR. Branches are `task/<id>-<few-words>`; commits and PR titles start with the task id (`M0.2: add fal smoke-test script`). The next-step skill does this; follow the same shape when working by hand.
- This repo uses the personal GitHub account `cmenguy` (menguy.charles@gmail.com); the local git config sets that author. The machine's active `gh` login is the work account, which cannot push here, so `GH_TOKEN` must carry the personal token: a git-ignored `.envrc` exports it (`export GH_TOKEN=$(gh auth token --hostname github.com --user cmenguy)`) and direnv loads it in the terminal. Claude Code's shell does not load direnv: when `echo ${GH_TOKEN:+set}` prints nothing, prefix `gh` and `git push` with `GH_TOKEN=$(gh auth token --hostname github.com --user cmenguy)`.
- Open the PR and report the link; merging is the owner's call. After a merge, `git checkout main && git pull --ff-only` before anything else.
- Never commit `.env`, `library/`, body models or checkpoints. `.gitignore` already covers them.

## Layout (GDD §8.2)

```
GDD.md  PLAN.md  README.md  CLAUDE.md
.claude/skills/   next-step, roadmap (and the plan parser)
godot/            Godot 4.x project: Gym + Workflow Manager         (from M2)
motionai/         Python package: CLI, pipeline stages, daemon      (from M1)
worker/           gvhmr-worker for the CUDA box, install scripts    (from M0.6)
library/          performers, clips, models; git-ignored
tests/            pytest; fixtures stay under 1 MB
docs/             feasibility, pipeline notes, findings, captures
```

Since M0.1 every directory exists with a one-line README; the annotations above say which milestone fills it in. `library/` is git-ignored except `library/README.md`. `.env.example` lists the secret names.

## Conventions

- Python 3.11 or later, `typer` CLI, `pydantic` models, `pytest`, `ruff`. Stage code under `motionai/stages/` has no CLI or HTTP concerns, so the CLI, the daemon and the tests share it.
- Godot 4.4 or later (`RetargetModifier3D`), pinned in `godot/project.godot`. One unit is one metre, Y-up, right-handed.
- Canonical skeleton: Godot `SkeletonProfileHumanoid` bone names on the 22 SMPL-X body joints (table in GDD §4 stage 5). Every library clip is a `motion.glb` on that skeleton; the mannequin and imported models are retargeted from it.
- Library layout per GDD §8.1: `library/clips/<id>/` holds `meta.json`, `takes/`, `selected.mp4`, `gvhmr/`, `motion.glb`, `qc.json`, `features.json`.
- Prompts for video generation end with "Static camera, full body visible." Cyclic locomotion is generated "on a treadmill"; root motion is added in cleanup.
- The Godot app never calls fal or the GPU worker directly. It talks to the local `motionai` daemon over HTTP and loads `.glb` files from the library.
- Secrets (`FAL_KEY`, `GVHMR_WORKER_TOKEN`, `ANTHROPIC_API_KEY`) live in `.env` or the OS keychain, never in the library, logs or git. `.env.example` lists the names.
- Anything calling Anthropic models (agent assist, M3.18) goes through the `claude-api` skill.

## Licensing guardrails

- GVHMR and SMPL-X are non-commercial research licenses. This is a prototype. Stage 4 stays behind the worker's `/extract` API so a licensed or commercial service can replace it.
- ComfyUI-MotionCapture is GPL-3.0: read it for reference, run it as a separate service, never copy its code into `motionai/`.
- The mannequin and any bundled asset must be CC0 or similarly permissive, with the license file stored next to the asset.

## Commands

```bash
python3 .claude/skills/next-step/scripts/plan.py next        # what to work on
python3 .claude/skills/next-step/scripts/plan.py summary     # progress
python3 .claude/skills/next-step/scripts/plan.py check       # validate PLAN.md
pytest                                                      # once motionai exists (M1.1)
motionai gen|extract|clean|export <args>                    # pipeline CLI (M1)
motionai serve                                              # local daemon for the Godot app (M3.7)
```

## Keeping the docs current

When a task changes the layout, the commands or a convention, update README.md and this file in the same change. The plan's Notes lines point at GDD sections; keep those pointers valid if the GDD is renumbered.
