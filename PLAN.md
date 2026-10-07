# Motion AI: Build Plan

| | |
|---|---|
| **Source** | [GDD.md](GDD.md) Draft v0.1 (2026-10-06) |
| **Created** | 2026-10-06 |
| **Tasks** | 63 across milestones M0 to M5 |
| **Tools** | `/next-step` picks and updates tasks, `/roadmap` summarises progress, both via `.claude/skills/next-step/scripts/plan.py` |
| **Companions** | [README.md](README.md) for the human-facing overview, [CLAUDE.md](CLAUDE.md) for session conventions |

This file is the single source of truth for *what to do next*. The GDD says what we are building and why; this plan says in what order and when each piece is done.

## How to read this file

- A **milestone** (`## M1: ...`) matches the GDD milestone table (§9) and has a milestone-level **Done when**.
- A **task** (`### M1.3 Title`) is a unit of work of half a day to a few days. Every task has:
  - **Status:** one of `todo`, `in-progress`, `done`, `blocked`, `skipped`.
  - **Depends on:** task IDs that must be `done` (or `skipped`) first. A task is *ready* when all its dependencies are finished.
  - **Component:** `repo`, `pipeline` (Python `anim8te` package), `worker` (GPU box), `godot` (Gym + Workflow Manager), `docs`, `decision`.
  - **Effort:** `S` under half a day, `M` one to two days, `L` three days or more, assuming an AI coding agent does most of the typing.
  - **Done when:** the acceptance check. Do not mark a task done without meeting it.
  - **Optional:** `yes` on tasks that can be skipped without blocking a milestone.
  - **Gate:** `yes` on tasks that need an explicit human go/no-go call.
- Update status with the script, which also appends a dated log line to the task:

  ```bash
  python3 .claude/skills/next-step/scripts/plan.py next                      # what to work on
  python3 .claude/skills/next-step/scripts/plan.py set M0.2 in-progress
  python3 .claude/skills/next-step/scripts/plan.py set M0.2 done --note "cost was $0.41 per take"
  python3 .claude/skills/next-step/scripts/plan.py summary                   # progress
  python3 .claude/skills/next-step/scripts/plan.py check                     # validate the file
  ```

Keep the field lines exactly in the `- **Field:** value` shape so the script can parse them. Free text goes in **Notes** or in the milestone intro.

Each task is one branch (`task/<id>-<few-words>`) and one pull request to `main` at https://github.com/cmenguy/anim8te; `main` is protected. The status change is part of the PR, so `main` lags open PRs. `/next-step` lists open PRs before picking, and never merges.

## Sequencing overview

```
M0 feasibility ──gate──> M1 pipeline CLI ──> M2 Gym viewer ──> M3.A cleanup + QC ──> M3.B daemon ──> M3.C Flow A UI ──> M4 Flow B ──> M5 starter set + controller ──> engine checkpoint
                              │                   ▲
                              └── M1.4 worker ────┘  (Godot setup M2.1 to M2.3 can start as soon as M0.8 is done, in parallel with M1)
```

Why this order, and where it departs from the GDD's milestone text:

1. **M0 is a gate, not a milestone of work.** Nothing in M1 or later is worth building if GVHMR output on AI-generated video is unusable (GDD §11). M0 runs GVHMR through the Apple-Silicon fork on the Mac (M0.10) and judges overlays and per-take metrics, so no pipeline code is written before the answer is in. The first in-Godot look at the motion is M1.11.
2. **M1 ships a *minimal* `clean` stage** (smoothing and ground alignment only). The GDD lists the full cleanup in stage 5, but foot locking, root motion, looping and segmentation can only be tuned against something you can see. So they move to **M3.A**, after the Gym exists, and before the Workflow Manager exposes them as toggles.
3. **M2 adds one pipeline task** (`features.json`, M2.7) because the Gym overlays need per-frame contacts and trajectories, and recomputing them in GDScript would duplicate the pipeline's logic.
4. **Two spikes are inserted** where the design has an unverified assumption: runtime GLB loading plus `RetargetModifier3D` (M2.4), and the Godot motion-matching addon (M5.2). Each one is a half-day check that protects a week of UI work.
5. **The daemon lands in M3.B**, not M1. The CLI alone is enough for M1 and M2 (the Gym reads the library from disk). The daemon exists for the UI, so it is built right before the UI needs it.
6. **The native GVHMR worker is the default extract backend** from M1 on (GDD §8). The ComfyUI backend stays optional (M1.12).

Parallel tracks once M0 passes: the Python pipeline (M1.x), the worker (M1.4), and Godot setup (M2.1 to M2.3) are independent until M2.4 joins them.

## Decisions

Open questions from GDD §11 plus the ones this plan surfaced. Status is `open`, `proposed` (a default is written in but not confirmed), or `decided`. The `/next-step` skill will ask for a decision when a ready task needs one.

| ID | Question | Status | Decision | Needed by |
|---|---|---|---|---|
| Q1 | Which CC0 mannequin becomes the default character? | decided | Quaternius Universal Base Characters (Standard, CC0), the male full-body glTF: UE-style 65-bone rig with fingers, every required `SkeletonProfileHumanoid` bone mappable; textures downscaled to 1024 px. Kenney's Animated Characters were the lighter alternative but coarser and less neutral | M2.3 |
| Q2 | GPU host for `gvhmr-worker`: always-on box vs spin-up per batch? | decided | Neither for now: GVHMR runs locally on the Mac through the Apple-Silicon fork (M0.10, about 30 s per static-camera take). A cloud CUDA box is deferred until moving-camera clips or batch volume need it, and would then be spin-up per batch | M0.6 |
| Q3 | Performer: one generic base image, or a Lara-like character from day one? | decided | One generic performer, `perf01` (woman in black tee and joggers standing on a treadmill deck), reused for every clip; a stylized character comes later by retargeting from the canonical skeleton | M0.4 |
| Q4 | Root-motion policy for treadmill loops: synthesized constant speed, or speed-matched to stride length? | open | | M3.2 |
| Q5 | Does the @MrCollison open-source parkour controller change the Controller plan? | open | | M5.2 |
| Q6 | Video playback in Godot for Compare mode: transcode takes to Ogg Theora, or add a video GDExtension? | decided | Transcode with ffmpeg in the pipeline (owner, 2026-10-07): `anim8te extract` writes `selected.ogv` and `gvhmr/overlay.ogv`, video only, mp4 stays the source of truth. Godot 4.7 still decodes only Theora. Needs an ffmpeg with libtheora; Homebrew's lacks it, so `brew install ffmpeg-full` (keg-only) | M2.9 |
| Q7 | Which Godot version to pin? `RetargetModifier3D` needs 4.4 or later | decided | Godot 4.7 (4.7.2 stable installed via Homebrew), pinned in `godot/project.godot` `config/features` | M0.8 |
| Q8 | Extract backend for M1: native GVHMR wrapper or ComfyUI workflow API? | decided | Native (owner, 2026-10-07): `worker/` wraps the fork's `gvhmr demo -s` as a subprocess and returns `hmr4d_results.pt` directly; ComfyUI stays optional and out of the pipeline | M1.4 |
| G0 | Go/no-go after M0: is GVHMR on H3 Max video good enough to build on? | decided | Go with conditions (owner, 2026-10-07): own contact detection and foot lock (M2.7, M3.1); one body shape per performer (M1.8, M3.5); leg-swap repair and travel rescale for dynamic clips (M3.20); still-camera clips only on the Mac worker (M1.4). See `docs/feasibility.md` "M0.9 Go/no-go" | M1.1 |

## M0: Accounts, GPU box, feasibility test

**Done when:** fal key works; GVHMR runs on the Mac through the Apple-Silicon fork; 3 to 5 H3 Max takes (idle, jog, vault) are extracted and judged from their overlays and per-take motion metrics; Godot is installed and pinned; the go/no-go decision is written down.
**Gate:** M0.9 go/no-go. If no-go, stop and rethink stages 2 and 4 (GDD §4) before any M1 work.

Everything here is throwaway except the base image, the takes, and the findings document. Accounts and license acceptances need the project owner, so several tasks will sit in `blocked` until those are done.

### M0.1 Scaffold the repo layout
- **Status:** done
- **Depends on:** none
- **Component:** repo
- **Effort:** S
- **Done when:** `godot/`, `anim8te/`, `worker/`, `library/`, `tests/`, `docs/` exist with a one-line README each; `.gitignore` still covers `library/`, `.env`, `.godot/`, `__pycache__/`, `*.ckpt`, `*.pt`, `*.npz`, `*.pkl` plus anything the scaffold adds; `.env.example` lists `FAL_KEY`, `GVHMR_WORKER_URL`, `GVHMR_WORKER_TOKEN`, `ANTHROPIC_API_KEY`; the layout sections of `README.md` and `CLAUDE.md` match what now exists on disk; merged to `main` through a PR.
- **Notes:** Layout from GDD §8.2. Git was initialised, `.gitignore` written and the remote set on 2026-10-06, so this task is only the directories and `.env.example`. `README.md` and `CLAUDE.md` already describe the target layout; this task makes the repo match them. The library stays git-ignored for now; revisit git-LFS once clips exist.
- **Log:** 2026-10-06 todo -> in-progress
- **Log:** 2026-10-06 in-progress -> done: 6 dirs with one-line READMEs; .env.example has the 4 names; .gitignore verified with check-ignore (library/* ignored except README); README/CLAUDE layout updated

### M0.2 fal account, API key and first H3 Max smoke test
- **Status:** done
- **Depends on:** M0.1
- **Component:** pipeline
- **Effort:** S
- **Done when:** `FAL_KEY` set in `.env`; a throwaway script under `docs/scratch/` generates one 5 s, 768P image-to-video clip from any full-body image with `fal_client.subscribe("minimax/h3-max/image-to-video", ...)` and saves the mp4; the real cost of that call is written in the Notes of this task.
- **Notes:** Needs the owner: create the key at https://fal.ai/dashboard/keys. Inputs and pricing in GDD §4 stage 2. Measured 2026-10-06: real cost $0.15 for the 5 s 768P clip ($0.03/s from fal's pricing API, under the GDD's $0.08/s estimate), plus about $0.002 for the flux/schnell base image. Walking toward the camera crops the feet by mid-clip; prefer side-on or treadmill prompts.
- **Log:** 2026-10-06 todo -> in-progress
- **Log:** 2026-10-06 in-progress -> blocked: waiting on owner: top up fal balance at https://fal.ai/dashboard/billing (key works, account locked: exhausted balance); then run docs/scratch/fal_smoke_test.py --gen-image
- **Log:** 2026-10-06 blocked -> in-progress
- **Log:** 2026-10-06 in-progress -> done: FAL_KEY in .env; docs/scratch/fal_smoke_test.py --gen-image saved a 768x1344 h264 5.18 s clip (124 frames @24fps); cost $0.15 ($0.03/s)

### M0.3 Register for SMPL-X and SMPL, download body models and GVHMR checkpoints
- **Status:** done
- **Depends on:** M0.1
- **Component:** worker
- **Effort:** S
- **Done when:** `SMPLX_{NEUTRAL,MALE,FEMALE}.npz`, the SMPL `.pkl` files, `gvhmr_siga24_release.ckpt`, the HMR2, ViTPose and YOLO checkpoints are downloaded into a directory outside git (for example `~/motion-ai-checkpoints/`, mirroring GVHMR's `inputs/checkpoints/` tree); the path and file sizes are listed in `docs/checkpoints.md`.
- **Notes:** Needs the owner: sign up and accept the non-commercial licenses at https://smpl-x.is.tue.mpg.de/ and https://smpl.is.tue.mpg.de/. The SMPL-X `.npz` files are also needed on the Mac for the `smplx` package in M1.6.
- **Log:** 2026-10-06 todo -> in-progress
- **Log:** 2026-10-06 in-progress -> done: 10 files (6.2 GB) in ~/motion-ai-checkpoints/ mirroring GVHMR inputs/checkpoints; SMPLX_NEUTRAL.npz loads (10475 verts, 400 shape+expr dirs); GVHMR ckpts from HF mirror camenduru/GVHMR (Drive quota hit), SHA256 match; sizes and hashes in docs/checkpoints.md

### M0.4 Choose the performer and make the base image
- **Status:** done
- **Depends on:** M0.1
- **Component:** pipeline
- **Effort:** S
- **Done when:** Q3 is decided; `library/performers/<performer_id>/base.png` exists and meets the stage 1 rules (full body with margin, locked-off camera at waist height, plain background, one person, fitted clothing); `library/performers/README.md` has the checklist and how the image was made.
- **Notes:** GDD §4 stage 1. Generating the image with an image model is fine; a photo is fine too. One performer for the whole library keeps body proportions constant across clips (GDD §11, identity drift risk).
- **Log:** 2026-10-06 todo -> in-progress
- **Log:** 2026-10-06 in-progress -> done: Q3 decided (generic perf01); library/performers/perf01/base.png (owner's GPT image, woman on a treadmill deck, 1122x1402, prompt in README) checked against stage 1: ~13%/30% margins top/bottom, straight-on but camera ~10 deg above eye level, one person, fitted clothes; textured concrete backdrop accepted; black-on-black feet flagged for M0.7-M0.9; README has checklist and provenance

### M0.5 Generate the feasibility takes: idle, jog, vault
- **Status:** done
- **Depends on:** M0.2, M0.4
- **Component:** pipeline
- **Effort:** S
- **Done when:** two or three takes each for idle (standing with subtle weight shifts), jog ("on a treadmill") and vault (waist-high block), 5 s at 768P with `prompt_expansion_mode` disabled and every prompt ending in "Static camera, full body visible."; files under `library/clips/<clip_id>/takes/<n>.mp4`; prompts, seeds, durations and cost logged in `docs/feasibility.md`.
- **Notes:** Prompting rules in GDD §4 stage 2. Budget is about $0.40 per take, so under $5 for the set. Keep the three movements: idle (static pose quality), jog (cyclic, loop quality), vault (dynamic, foot contact and root height).
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: idle 2, jog 3, vault 3 takes (5 s, 768P, expansion off) under library/clips/{idle,jog,vault}-m05/takes/; vault redone side-on from perf01/vault/base.png (camera pans to follow); prompts, seeds, wall clock and $2.55 total logged in docs/feasibility.md

### M0.6 Provision the cloud GPU box and install ComfyUI + ComfyUI-MotionCapture
- **Status:** skipped
- **Depends on:** M0.3
- **Component:** worker
- **Effort:** M
- **Done when:** Q2 decided; a CUDA box (24 GB VRAM or more recommended) runs ComfyUI with ComfyUI-MotionCapture installed by hand (not the experimental one-click installer); checkpoints from M0.3 in place; `workflows/GVHMR.json` loads with no missing nodes; `worker/README.md` records the host, image, hourly cost and every install step so the box can be rebuilt from scratch.
- **Notes:** GDD §4 alternative and §8. Needs the owner: account and billing on RunPod, Lambda or similar. Keep an install script (`worker/setup_comfyui.sh`) rather than only notes, since spin-up-per-batch (Q2) means rebuilding often.
- **Log:** 2026-10-07 todo -> skipped: owner skipped it: GVHMR runs on the Mac through the Apple-Silicon fork (M0.10); Q2 decided, cloud box deferred; M0.7 repointed to overlays and metrics, M0.8 to Godot install only, M1.4 to the Mac

### M0.7 Judge the feasibility takes from overlays and motion metrics
- **Status:** done
- **Depends on:** M0.10
- **Component:** pipeline
- **Effort:** S
- **Done when:** a throwaway script under `docs/scratch/` reads each take's `hmr4d_results.pt` from M0.10 and reports per take: foot sliding while a foot is in contact (cm per frame), frame-to-frame jitter of the joints, root height over time (the vault should rise by about the block height), and treadmill drift for the jog; each take's `1_incam.mp4` and `2_global.mp4` overlays are reviewed for limb flips, missing frames and body-shape drift between takes; numbers and observations are recorded per take in `docs/feasibility.md`.
- **Notes:** Repointed from the ComfyUI `GVHMR.json` run when M0.6 was skipped (Q2). No GLB in M0: turning `hmr4d_results.pt` into a skeleton animation is M1.6 to M1.10, and M1.11 is the first in-Godot check. Joint positions need the SMPL-X body model from M0.3; run the script with the fork's `.venv` (it has torch and the body-model code), not inside `anim8te/`.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: docs/scratch/judge_takes.py on 7 takes: no missing frames or >45° flips; foot slide idle 0.2-0.3, jog 1.1-1.6, vault 0.6-0.9 cm/frame; jog drift 5-10 cm/5 s; vault soles +0.55/+0.59 m vs ~0.53 m block; vault run-up leg swaps and ~30% overlong travel; stature 1.67-1.73 m across takes; recorded in docs/feasibility.md

### M0.8 Install Godot and pin the version
- **Status:** done
- **Depends on:** M0.1
- **Component:** godot
- **Effort:** S
- **Done when:** Q7 decided and Godot installed on the Mac; an empty project under `godot/` opens with the version pinned in `godot/project.godot`, one unit one metre, Y-up.
- **Notes:** The feasibility GLB import was dropped when M0.6 was skipped; the first motion in Godot is M1.11. M2.1 to M2.3 start from this project.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: Godot 4.7.2 stable installed (Homebrew cask); godot/project.godot pins features 4.7 and opens headless in the 4.7.2 editor with no errors; runtime check: Vector3.UP=(0,1,0), right-handed; Q7 decided

### M0.9 Go/no-go decision
- **Status:** done
- **Depends on:** M0.7
- **Component:** decision
- **Effort:** S
- **Gate:** yes
- **Done when:** `docs/feasibility.md` has a "Go/no-go" section stating go or no-go, the evidence, and if no-go which of stages 2 (video) or 4 (extraction) to rethink and with what alternatives; decision G0 in the table above is set to `decided`. Only the owner makes this call; the agent prepares the evidence.
- **Notes:** GDD §9 M0 and §11. Alternatives if no-go: a different video model, stricter prompts, or a commercial video-to-mocap service behind the same `/extract` interface (GDD §10).
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: owner call 2026-10-07: go with conditions; G0 decided; docs/feasibility.md 'M0.9 Go/no-go' section; conditions mapped to M2.7, M3.1, M1.8, M3.5, new M3.20, M1.4

### M0.10 Spike: run the Apple-Silicon GVHMR fork on the Mac
- **Status:** done
- **Depends on:** M0.3, M0.5, M0.11
- **Component:** worker
- **Effort:** S
- **Done when:** `ryanrudes/gvhmr` is installed on the Mac outside the repo at a recorded commit, using the M0.3 checkpoints and body models, and `gvhmr info` reports MPS with no missing assets; every M0.5 take has `hmr4d_results.pt` and an overlay video under `library/clips/<clip_id>/feasibility/` (idle and jog with `-s`; vault on the M0.11 still-camera takes 2 and 3 with `-s`, since the v2 takes pan and `--camera vggt` exhausted the Mac's 48 GB); per-take wall time, flags and failures are recorded in `docs/feasibility.md` with a recommendation on whether the Mac replaces the cloud box (Q2, M0.6).
- **Notes:** The fork (https://github.com/ryanrudes/gvhmr) claims MPS support end to end and byte-identical results to upstream on the default path; only DPVO is CUDA-only. Same non-commercial GVHMR license; run it as a separate tool, never copy its code into `anim8te/`. If the spike works, M0.6 is skipped and M0.7 is repointed at the local run (it loses ComfyUI's GLB node; overlays are enough to judge quality, and GLB export is M1 work). If it fails, M0.6 goes ahead as planned.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: fork e387609 at ~/motion-ai-tools/gvhmr, gvhmr info MPS; hmr4d_results.pt + overlays for idle 2-3, jog 1-3, vault 2-3 (-s, ~30 s each); VGGT on panning vault v2/3 hit 50 GB and panicked the Mac; recommendation in docs/feasibility.md: Mac replaces the cloud box for static-camera clips

### M0.11 Wide vault base image so the camera can stay still
- **Status:** done
- **Depends on:** M0.5
- **Component:** pipeline
- **Effort:** S
- **Done when:** `library/performers/perf01/vault/base.png` is a wide shot with her whole path (run-up to landing on the block) in frame, made by a masked fill of `comp7.png` and logged in `candidates/manifest.json`; the v2 takes are moved to `takes/v2/`; three new vault takes from it with the v2 prompt and settings sit at `library/clips/vault-m05/takes/<n>.mp4`; `docs/feasibility.md` records the fill calls, the takes, their cost and whether the camera stays still in each.
- **Notes:** The v2 takes pan to follow her because she fills about 80% of the frame height and runs out of it; the prompt's "Camera remains perfectly still" loses to "full body visible". Idle and jog stay in place, so they never hit this. Any traveling move will, so the result also tells the GDD §4 stage 2 prompting rules whether wide base images are enough or whether traveling moves are handled as moving-camera clips.
- **Log:** 2026-10-07 in-progress -> done: base.png is cand10 (comp7 fill, flux-pro/v1/fill); v2 takes in takes/v2/; 3 new takes, 2 and 3 with a still camera, 1 pushes in; fills and takes $0.67 logged in docs/feasibility.md

## M1: Pipeline CLI, one clip

**Done when:** `anim8te gen && anim8te extract && anim8te clean && anim8te export` turns one prompt into `motion.glb` that imports into Godot on the humanoid profile.

The pipeline is a Python package with pure stage functions and a thin CLI on top, so that the daemon (M3.B) and tests reuse the same code. Stage 5 cleanup is deliberately minimal here; see the sequencing overview.

### M1.1 Python package skeleton and CLI
- **Status:** done
- **Depends on:** M0.9
- **Component:** pipeline
- **Effort:** M
- **Done when:** `anim8te/` is an installable package (`pyproject.toml`, Python 3.11 or later, `uv` or `pip -e`); `anim8te --help` lists `gen`, `extract`, `clean`, `export`, `lib`; configuration loads from `.env` then `~/.config/anim8te/config.toml`; the library root resolves from config or `--library`; `pytest` runs one trivial test; `ruff` is configured; `tests/` and `anim8te/stages/` exist.
- **Notes:** GDD §8. Use `typer` for the CLI. Keep stage code free of CLI concerns so M3.7 can call it from a job runner.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: uv sync and pip -e install; anim8te --help lists gen/extract/clean/export/lib; settings: --library > env > .env > ~/.config/anim8te/config.toml (no secrets) > ./library, checked by 'lib path' and tests; pytest 3 passed; ruff check and format clean

### M1.2 Library data model: meta.json and qc.json schemas
- **Status:** done
- **Depends on:** M1.1
- **Component:** pipeline
- **Effort:** S
- **Done when:** `pydantic` models for `meta.json` (name, tags, performer, template, prompt, final prompt, takes with seed/cost/duration/resolution, selected take, filters, segments, loop, root-motion mode, status, parent clip) and a placeholder `qc.json`; `anim8te lib ls` lists clips and performers with status; a test round-trips a meta.json through the model.
- **Notes:** Layout from GDD §8.1. Clip IDs: short slug plus a timestamp or random suffix, so re-generating "vault" never collides.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: anim8te/library.py: ClipMeta (all listed fields, enums for template/root-motion/status, consistency checks), placeholder QCReport, atomic write, <slug>-<6 chars> ids; anim8te lib ls lists clips and performers with status (run on the real library: 3 pre-M1 clips show 'no meta.json', perf01 ok); tests/test_library.py round-trips tests/fixtures/meta.json, 10 tests pass, ruff clean

### M1.3 anim8te gen: fal client, prompt templates and takes
- **Status:** done
- **Depends on:** M1.2, M0.2
- **Component:** pipeline
- **Effort:** M
- **Done when:** `anim8te gen --performer <id> --template locomotion|traversal|combat|custom --prompt "..." --takes 3 --duration 5 --resolution 768P [--seed N]` creates a clip directory, uploads the base image once, generates takes concurrently, writes `takes/<n>.mp4` and `meta.json` with seeds and cost; templates append the camera rule and (locomotion) the treadmill rule; `--dry-run` prints the final prompt and estimated cost; failures retry with backoff and leave meta.json consistent.
- **Notes:** GDD §4 stage 2. Templates live in `anim8te/templates/*.toml` so the UI (M3.12) and the agent assist (M3.18) read the same rules.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: 32 tests pass (templates, dry-run, retry/backoff, partial and total failure keep meta.json consistent); live run walk-ur7zdb: 3/3 takes 768x960 24fps 5.18 s, one upload, $0.45 at $0.03/s, walking in place on the treadmill, full body, static camera

### M1.4 gvhmr-worker: native FastAPI wrapper around GVHMR demo.py
- **Status:** done
- **Depends on:** M0.10
- **Component:** worker
- **Effort:** M
- **Done when:** Q8 decided; `worker/` has a `Dockerfile` or `setup.sh` that installs GVHMR and expects the M0.3 checkpoints at a mounted path; `POST /extract` (multipart video, bearer token, `static_camera=true`) returns a job id; `GET /jobs/{id}` returns `queued|running|done|failed`, log tail, and when done the download URLs for `hmr4d_results.pt` and `overlay.mp4`; one M0 take runs through it on the Mac (Apple-Silicon fork, MPS); `worker/README.md` documents start-up and the API.
- **Notes:** GDD §8. Runs the fork's `gvhmr demo <video> -s` on the Mac (Q2; install notes in `docs/feasibility.md`, M0.10), or upstream `tools/demo/demo.py --video ... -s` on a CUDA box later. Keep the API tiny so a commercial service (Move.ai, Rokoko, DeepMotion) can replace it later (GDD §10). No GPL code in here. Per G0, the Mac worker accepts still-camera takes only: a moving-camera request is refused with a clear error, never run through VGGT or DUSt3R at their defaults (that crashed the Mac in M0.10); those go to a CUDA box or are avoided through framing.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: Q8 decided native; worker/setup.sh installs the pinned fork + worker (ran on the Mac); idle-m05/3 through POST /extract -> done in 36 s on MPS, hmr4d_results.pt (155x63 body_pose) and overlay.mp4 downloaded, overlay checked; 401 without token, 422 on static_camera=false; 11 worker tests pass. Found: without ffprobe GVHMR treats 24 fps takes as 30 fps (M0.10 outputs were 124 frames, worker gives 155)

### M1.5 anim8te extract: worker client
- **Status:** done
- **Depends on:** M1.3, M1.4
- **Component:** pipeline
- **Effort:** S
- **Done when:** `anim8te extract <clip_id> [--take n]` marks the selected take, uploads it, polls with progress, downloads to `gvhmr/hmr4d_results.pt` and `gvhmr/overlay.mp4`, and updates `meta.json`; worker unreachable, bad token and failed jobs produce clear messages and leave the clip re-runnable.
- **Notes:** GDD §4 stage 4.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: 43 tests pass (fake worker: happy path, rerun, failed job, failed download, 401, unreachable, timeout); real run on walk-ur7zdb take 1: 32 s on the Mac worker, gvhmr/hmr4d_results.pt (155 frames) + overlay.mp4, meta status extracted; real 401, unreachable and failed-job messages checked, failures leave meta.json untouched

### M1.6 Load SMPL-X parameters and rebuild joints
- **Status:** done
- **Depends on:** M1.5, M0.3
- **Component:** pipeline
- **Effort:** M
- **Done when:** `anim8te.convert.load_gvhmr(path)` returns per-frame `global_orient`, `body_pose`, `transl`, `betas` and the frame rate as numpy arrays; the `smplx` package rebuilds the 22 body joint positions and parent table from `betas`; a test on a small fixture (`tests/fixtures/*.pt`, under 1 MB, trimmed from a real output) checks shapes, joint count and frame rate.
- **Notes:** GDD §4 stage 5.1. We only use `smpl_params_global`. GVHMR's demo resamples every input to 30 fps (it is a 30 fps model), so the parameters are always 30 fps, not the source video's rate (a 124-frame 24 fps take gives 155 frames).
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: load_gvhmr on real walk-ur7zdb output: 155 frames at 30 fps (GVHMR resamples the 24 fps take), body_pose (T,21,3), betas (10,); rest_skeleton via smplx gives 22 joints with SMPL parents, ankle-to-head 1.47 m; tests/test_convert.py on a 5.5 KB 10-frame fixture, 47 tests pass

### M1.7 Axis conventions: GVHMR world frame to glTF
- **Status:** done
- **Depends on:** M1.6
- **Component:** pipeline
- **Effort:** S
- **Done when:** the up axis and handedness of GVHMR's world frame are verified on a real clip (feet near the ground plane, head above hips, forward matching the video); `to_gltf_frame()` converts positions and rotations to Y-up, right-handed, metres; a unit test pins the convention with a known standing pose; the finding is written in `docs/pipeline-notes.md`.
- **Notes:** GDD §4 stage 5.2. Getting this wrong silently breaks everything downstream, which is why it is its own task with its own test.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: GVHMR world is Y-up right-handed metres, +Z away from camera (hmr_global.py get_R_c2gv + any->ay); to_gltf_frame = 180° about Y; verified on 8 real clips (facing-camera clips face +Z, vault faces/travels +X = screen right as in video); 52 tests pass; docs/pipeline-notes.md

### M1.8 Canonical skeleton: SkeletonProfileHumanoid names on the SMPL-X tree
- **Status:** done
- **Depends on:** M1.7
- **Component:** pipeline
- **Effort:** M
- **Done when:** `anim8te/skeleton.py` defines the hierarchy of the 22 SMPL-X body joints renamed with the humanoid names from the GDD table (Hips, Spine, Chest, UpperChest, Neck, Head, Left/Right Shoulder, UpperArm, LowerArm, Hand, UpperLeg, LowerLeg, Foot, Toes), rest pose built from the performer's `betas`, parent indices; a test checks every SMPL-X joint maps to exactly one humanoid name and the parent table forms a single tree rooted at Hips.
- **Notes:** GDD §4 stage 5.3. Rest pose is the SMPL-X zero pose with the performer's shape, so GVHMR's local rotations transfer without re-expression. Godot's humanoid retarget (import-time "overwrite axis" and "fix silhouette", runtime `RetargetModifier3D`) absorbs the difference to the mannequin's rest. No fingers. Per G0, `betas` are fixed per performer (stored once with the performer, reused by every clip), not taken from each clip: M0.7 measured a 6 cm stature spread across clips of the same performer.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: anim8te/skeleton.py: 22 SMPL-X joints -> SkeletonProfileHumanoid names, SMPL-X parents rooted at Hips, rest pose from betas via smplx (fixture shape: 1.53 m toes to head joint, left +X, toes +Z); per-performer betas.json set by first clip; tests/test_skeleton.py 7 pass with the body model, 59 total

### M1.9 Minimal anim8te clean: smoothing and ground alignment
- **Status:** done
- **Depends on:** M1.8
- **Component:** pipeline
- **Effort:** S
- **Done when:** `anim8te clean <clip_id>` applies One-Euro (or Savitzky-Golay) smoothing to rotations and hips translation, then ground alignment (lowest foot or toe height over the clip, using a low percentile, moved to y = 0); filter toggles and parameters are read from and written to `meta.json`; re-running is idempotent; a test shows a jittered synthetic signal gets smoother and the minimum foot height is about 0.
- **Notes:** GDD §4 stage 5.4. The rest of the filters (foot lock, root motion, loop, segmentation, QC) are M3.A.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: anim8te/stages/clean.py + CLI: Savitzky-Golay (9 frames, order 3) on bone quaternions and Hips translation, ground alignment of the 5th-percentile sole height to y=0; filters read from and written to meta.json; idempotent (re-run gives identical arrays); tests/test_clean.py 13 pass (jitter left <10%, sole p5 = 0), 70 total; walk-ur7zdb: 155 frames, lowered 8.9 cm, joint accel energy halved, max smoothing shift 2.4 cm, sole p5 0.0 cm / median 0.9 cm

### M1.10 anim8te export: write motion.glb
- **Status:** done
- **Depends on:** M1.9
- **Component:** pipeline
- **Effort:** M
- **Done when:** `anim8te export <clip_id>` writes `motion.glb` with `pygltflib`: skin, nodes with rest transforms from M1.8, one animation named after the clip with rotation channels for every bone and a translation channel for Hips, correct frame timing; the file passes the Khronos glTF-Validator with no errors; dragging it into a Godot project auto-detects the humanoid bone map with all 22 bones mapped and plays on a `Skeleton3D`.
- **Notes:** GDD §4 stage 5.7. No mesh is required in the library GLB; a skeleton-only glTF is valid and keeps files small. Add a tiny placeholder mesh only if Godot's importer needs one. Reference only: GVHMR issue #84 (https://github.com/zju3dv/GVHMR/issues/84) shares a `bpy` script that exports `smpl_params_global` to GLB; useful to cross-check our SMPL-to-rotation conversion on one clip, not to adopt (needs `bpy` 4.4 on Python 3.11 against GVHMR's 3.10, patches GVHMR, ships the SMPL mesh, no stated license).
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: anim8te export walk-ur7zdb -> 66 KiB skeleton-only motion.glb (155 frames, 30 fps, 23 channels); Khronos glTF-Validator 2.0.0-dev.3.10: 0 errors, 0 warnings (1 info: skin unused, no mesh); Godot 4.7 headless import: 22-bone Skeleton3D matching SkeletonProfileHumanoid, animation walk-ur7zdb 5.13 s; owner confirmed in the editor: auto bone map 22/22, plays; 75 tests pass

### M1.11 End-to-end: one prompt to motion.glb in Godot
- **Status:** done
- **Depends on:** M1.10
- **Component:** pipeline
- **Effort:** S
- **Done when:** a fresh clip goes `gen`, `extract`, `clean`, `export` from the CLI in under about 20 minutes wall-clock; a short capture of the GLB playing in Godot is saved under `docs/captures/`; per-stage timings and costs are written in `docs/pipeline-notes.md`. This closes M1.
- **Notes:** GDD goal G1.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: jog-qa61r5: gen 19 s/$0.45, extract 38 s, clean 2 s, export 1 s, 75 s prompt to motion.glb; Godot 4.7 capture docs/captures/m1-jog-qa61r5-godot.mp4 (22 bones, 5.13 s loop); timings in docs/pipeline-notes.md

### M1.12 ComfyUI backend for gvhmr-worker
- **Status:** todo
- **Depends on:** M1.4
- **Component:** worker
- **Effort:** M
- **Optional:** yes
- **Done when:** `GVHMR_WORKER_BACKEND=comfyui` makes the worker submit the M0 `GVHMR.json` workflow through ComfyUI's `/prompt` API and return the same outputs as the native backend; both backends pass the same smoke test.
- **Notes:** GDD §8. Only worth doing if the native wrapper proves fragile, or for its debugging viewers. Must run as a separate service so GPL-3.0 code stays out of `anim8te`.

## M2: Gym, Clip Viewer and Compare

**Done when:** library clips play on the default mannequin with debug overlays; Compare view shows source video, GVHMR overlay and the 3D clip frame-synced.

The Gym reads the library straight from disk in this milestone; the daemon comes in M3.B. Tasks M2.1 to M2.3 only need Godot and can start as soon as M0.8 is done, in parallel with M1.

### M2.1 Godot project setup
- **Status:** done
- **Depends on:** M0.8
- **Component:** godot
- **Effort:** S
- **Done when:** `godot/project.godot` on the pinned version (Q7), Forward+ renderer, a main scene, folders `scenes/`, `scripts/`, `assets/`, `ui/`, `addons/`; `.godot/` ignored; a `godot/README.md` with how to open and run; the project opens and runs with no errors or warnings.
- **Notes:** GDD §5 and §8.2.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: Godot 4.7.2: clean --import and a windowed run (Metal 4.0, Forward+) exit 0 with 0 warning/error lines; main scene scenes/main.tscn, folders scenes/ scripts/ assets/ ui/ addons/, godot/README.md says how to open and run

### M2.2 Calibration level grey-box
- **Status:** done
- **Depends on:** M2.1
- **Component:** godot
- **Effort:** M
- **Done when:** a 40 x 40 m ground plane with a 1 m grid and 10 cm sub-grid shader; boxes at 0.5, 1.0 and 1.5 m; a 2.2 m ledge wall; gaps of 1.5, 2.5 and 3.5 m between platforms; 20° and 35° ramps; a staircase with 0.18 m risers; a 0.3 m beam; every prop labelled with its size; neutral sky (a `ProceduralSkyMaterial`; the owner chose the simplest option over an HDRI asset), one directional light, ACES tone mapping; an orbit camera with focus-on-character.
- **Notes:** GDD §6.1. One Godot unit is one metre. Build props from `CSGBox3D` or `MeshInstance3D` with collision so M5's controller can use them.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: headless check: boxes 0.5/1.0/1.5 m, ledge 2.2 m, gaps 1.50/2.50/3.50 m, ramps 20.0/35.0 deg, 8 risers of 0.18 m, beam 0.3 m, all StaticBody3D with collision and size labels; ACES + procedural sky + 1 directional light; renders from 5 orbit views and F-focus checked

### M2.3 Default mannequin on the humanoid profile
- **Status:** done
- **Depends on:** M2.1
- **Component:** godot
- **Effort:** M
- **Done when:** Q1 decided; a CC0 humanoid mesh imported under `godot/assets/mannequin/` with its license file; import settings use `SkeletonProfileHumanoid` with a `BoneMap` where all required bones are mapped, bones renamed, "overwrite axis" and "fix silhouette" on; a library clip from M1 plays on it through the editor import path.
- **Notes:** GDD §6.2. Candidates: Quaternius CC0 humanoids, Kenney characters, or a neutral mannequin from a CC0 pack. Avoid the SMPL-X mesh (license).
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: Q1 decided (Quaternius Universal Base Characters, male, CC0, LICENSE.txt alongside); import: BoneMap on SkeletonProfileHumanoid, 53/56 bones mapped, all 17 required, renamed, %GeneralSkeleton, Overwrite Axis + fix silhouette; walk-ur7zdb imported as AnimationLibrary (23 tracks on %GeneralSkeleton) loops on the mannequin in scenes/mannequin_preview.tscn, checked on Movie Maker frames

### M2.4 Spike: runtime GLB load and RetargetModifier3D onto the mannequin
- **Status:** done
- **Depends on:** M2.3, M1.10, M2.12
- **Component:** godot
- **Effort:** M
- **Done when:** a script loads `library/clips/<id>/motion.glb` at runtime with `GLTFDocument`, finds its `Skeleton3D` and `AnimationPlayer`, and drives the mannequin through `RetargetModifier3D` using the humanoid profile; bone renaming at runtime (if needed) is handled; `godot/README.md` has a "Runtime retargeting" section with the gotchas and the chosen node layout.
- **Notes:** This is the main Godot risk for the Clip Viewer and for Flow B (M4). Do it before building UI on top. If runtime retargeting fails, the fallback is to bake clips onto the mannequin's skeleton in the pipeline, which changes M1.10 and M4.5.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: ClipPlayer: GLTFDocument load + clip re-expressed on the model's rest + RetargetModifier3D (local, model Skeleton3D as direct child); no renaming needed; tests/check_runtime_retarget.gd PASS on walk-ur7zdb + jog-qa61r5: bone directions 0.00 deg and hip height change 0.00 cm vs the clip (editor path 3-14 deg off); README Runtime retargeting; capture docs/captures/m2.4-runtime-retarget.jpg

### M2.5 Library scanner and clip list
- **Status:** done
- **Depends on:** M2.4
- **Component:** godot
- **Effort:** S
- **Done when:** on start and on refresh the Gym scans `library/clips/*/` for `meta.json`, `qc.json` and `motion.glb`, builds a clip list with name, tags, status and QC badge; the library path is configurable; missing or partial clips are shown as such rather than crashing.
- **Notes:** GDD §7.2 Library panel, in its simplest form. The daemon-backed version is M3.10.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: tests/check_library_scanner.gd PASS (17 checks: complete, no-qc, no-glb, no-meta, corrupt meta/qc, empty dir, missing root, refresh, selection); real library lists 5 clips, 3 partial; --library/ANIM8TE_LIBRARY/path field verified; check_runtime_retarget still PASS; capture docs/captures/m2.5-library-panel.jpg

### M2.6 Clip Viewer mode
- **Status:** done
- **Depends on:** M2.5
- **Component:** godot
- **Effort:** M
- **Done when:** selecting a clip plays it on the mannequin in the calibration level; timeline scrub, play/pause, speed from 0.1x to 2x, loop toggle, frame step forward/back, current frame and time shown; the camera can follow the character; switching clips is instant.
- **Notes:** GDD §6.3.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: tests/check_clip_viewer.gd PASS (36 checks: play/pause, step +/-1 with loop wrap and end clamp, scrub to frame 77 moves the hips, 0.1x-2x speed, loop off stops on last frame, follow keeps the orbit centre on the hips within 2 mm, switch 10 ms first load / 0.15 ms cached); retarget and scanner checks still PASS; capture docs/captures/m2.6-clip-viewer.jpg

### M2.7 Pipeline: per-frame features for overlays (features.json)
- **Status:** done
- **Depends on:** M1.9
- **Component:** pipeline
- **Effort:** M
- **Done when:** `anim8te clean` also writes `features.json` with per-frame foot and toe contacts (height plus velocity thresholds, per side), root position and velocity, joint positions in the canonical frame (metres), per-joint jerk; thresholds live in config; a test on a synthetic walking signal detects alternating contacts.
- **Notes:** GDD §4 stage 5.4 contact detection and §6.4. Detection only; the foot-lock fix is M3.1. The Gym reads this file instead of recomputing, so the UI and the QC numbers agree.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: 85 tests pass (test_features: synthetic treadmill and overground walk, alternating contacts, >90% stance agreement); anim8te clean writes features.json (~110 KB); walk-ur7zdb and jog-qa61r5 show alternating L/R contacts with auto ground velocity -0.79/-0.89 m/s (treadmill belt); thresholds in meta.json filters.contacts (height 0.04 m, speed 0.8 m/s, min 3 frames); re-run byte-identical

### M2.8 Debug overlays
- **Status:** done
- **Depends on:** M2.6, M2.7
- **Component:** godot
- **Effort:** M
- **Done when:** per-overlay toggles for foot-contact markers (green planted, red sliding), root trajectory (past and predicted), velocity vectors, ground-penetration highlight, skeleton wireframe and joint-jerk heatmap; each overlay is its own node reading `features.json`; toggles persist across clip changes and sessions.
- **Notes:** GDD §6.4. The motion-matching pick and cost overlay is M5.4.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: 6 overlays (contacts, trajectory, velocity, penetration, wireframe, jerk) each a DebugOverlay node on features.json; check_overlays.gd matches the file on every frame of walk and jog, toggles kept across clip change and a new session (user://gym_settings.cfg), keys 1-6; jog 56% sliding vs walk 35%, jog toes 8 mm under on f86-87; features.json gains rest_heights_above_sole; capture docs/captures/m2.8-debug-overlays.jpg

### M2.9 Video for Godot: transcode takes and the GVHMR overlay to Ogg Theora
- **Status:** done
- **Depends on:** M1.5
- **Component:** pipeline
- **Effort:** S
- **Done when:** Q6 decided; `anim8te extract` writes `selected.ogv` and `gvhmr/overlay.ogv` with ffmpeg (libtheora, same frame rate and size as the source); a missing ffmpeg gives a clear error; Godot's `VideoStreamPlayer` plays both files.
- **Notes:** Godot 4 only decodes Ogg Theora out of the box. The mp4 files stay the source of truth.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: Q6 decided (transcode); real extract via worker wrote selected.ogv + gvhmr/overlay.ogv, ffprobe-checked same size/rate/frames (768x960@24 124f, 768x480@30 155f); missing or theora-less ffmpeg -> clear error before upload; check_video_playback.gd passes on walk and jog (play, rate, 3 s seek, end); needs brew ffmpeg-full; 93 pytest pass

### M2.10 Compare mode: frame-synced source, overlay and 3D
- **Status:** todo
- **Depends on:** M2.8, M2.9
- **Component:** godot
- **Effort:** M
- **Done when:** a split view with the source take, the GVHMR overlay video and the 3D clip; scrubbing the shared timeline seeks all three; drift stays under one frame over a 5 s clip; speed and loop apply to all three.
- **Notes:** GDD §6.3. `VideoStreamPlayer` seeking is coarse; driving `stream_position` from the animation time every frame is the likely approach.

### M2.11 Review the M0 and M1 clips in the Gym and log findings
- **Status:** todo
- **Depends on:** M2.10
- **Component:** docs
- **Effort:** S
- **Done when:** every clip so far has been viewed in Clip Viewer and Compare; `docs/gym-findings.md` lists defects per clip (foot skate, ground penetration, jitter, root drift, limb flips) with timestamps; the list ranks which cleanup filters matter most, which sets the order of M3.A. This closes M2.
- **Notes:** GDD §3.2: the gym with overlays is the fastest way to see what still breaks.

### M2.12 Export: straight-spine rest so humanoid retargeting keeps posture
- **Status:** done
- **Depends on:** M1.10
- **Component:** pipeline
- **Effort:** S
- **Done when:** `anim8te export` writes `motion.glb` with the Spine, Chest, UpperChest, Neck and Head rest offsets vertical (same lengths, rotations unchanged), documented in `docs/pipeline-notes.md` and covered by `tests/test_export.py`; the M1 clips are re-exported and `godot/assets/sample_clips/walk-ur7zdb.glb` refreshed; on the mannequin the walk's Chest>UpperChest lean is within about 15 degrees of vertical (it is 35 to 38 degrees today).
- **Notes:** Found in M2.3. SMPL-X's rest spine is kinked (the UpperChest joint sits behind Chest: 27 degrees forward at rest, -10 at the neck). Godot's "overwrite axis" retarget transfers bone directions rather than deltas from rest, so that kink lands on the mannequin as a hunch with the head pushed forward. A scratch copy with the five spine offsets straightened walked upright (upper back 9 to 11 degrees, neck -4 to -6, head 6 to 7). M2.4 uses the same profile path, so it depends on this.
- **Log:** 2026-10-07 todo -> in-progress
- **Log:** 2026-10-07 in-progress -> done: export.py STRAIGHT_BONES: Spine..Head rest offsets vertical, lengths kept, rotations unchanged; tests/test_export.py 5 pass (76 total), ruff clean; walk-ur7zdb + jog-qa61r5 re-exported, sample_clips/walk refreshed; mannequin Chest>UpperChest lean per frame 5.5-12.2 deg (median 9.8), was 32.9-39.9 (median 37.1); docs/pipeline-notes.md

### M2.13 Playable grey-box: blend-tree controller over the current clips
- **Status:** todo
- **Depends on:** M2.3, M2.2
- **Component:** godot
- **Effort:** M
- **Done when:** the mannequin on a `CharacterBody3D` in the calibration level moves with WASD relative to a third-person follow camera; an `AnimationTree` blends idle, walk and jog by speed (sprint key for jog) from the library clips imported through the editor path (`assets/sample_clips/`, canonical bone map); a key triggers the vault clip; collision with the props works; `godot/README.md` says how to play; a short capture is saved under `docs/captures/`.
- **Notes:** Owner's request (2026-10-07): something playable in the grey box early, with the clips that exist today (idle-m05, walk-ur7zdb, jog-m05 or jog-qa61r5, vault-m05). Only walk-ur7zdb and jog-qa61r5 have a `motion.glb`; idle-m05, jog-m05 and vault-m05 hold M0 feasibility takes only, so they go through `anim8te extract`, `clean` and `export` first (the M0 outputs may need a `meta.json`). Once M2.4 is merged, `ClipPlayer` can load them at runtime instead of copying them under `assets/sample_clips/`. Uses editor imports, so it does not need M2.4. Hand-built blend tree, no motion matching; M5.3 stays the real controller over the starter set. Root motion is optional here (in-place clips plus code-driven velocity is fine).

## M3: Workflow Manager, Flow A

**Done when:** a new animation goes from prompt to library entirely from the UI; the Jobs screen shows cost and status.

Three phases. **M3.A** finishes the stage 5 cleanup in the pipeline, tuned against the Gym. **M3.B** wraps the pipeline in the local daemon. **M3.C** builds the Workflow Manager UI around the Gym viewport.

**Phase M3.A: cleanup, QC and segmentation (pipeline)**

### M3.1 Foot locking with two-bone IK during contacts
- **Status:** todo
- **Depends on:** M2.7, M2.11
- **Component:** pipeline
- **Effort:** L
- **Done when:** during each detected contact the foot is pinned to its first-contact position with two-bone IK on hip, knee and ankle (pole vector from the original knee direction), with blend-in and blend-out windows; toggle and parameters in `meta.json`; on the jog and vault clips the foot-skate metric (M3.5) drops clearly and joint jerk does not rise (no knee pops); visible in the Gym overlays.
- **Notes:** GDD §4 stage 5.4 and §11 foot skate risk.

### M3.2 Root motion: hips extraction and treadmill synthesis
- **Status:** todo
- **Depends on:** M2.7
- **Component:** pipeline
- **Effort:** M
- **Done when:** Q4 decided; `root_motion_mode` in `meta.json` is one of `none`, `from_hips`, `synthesized`; `from_hips` moves the hips' XZ translation and yaw into a root track and leaves the local hips motion; `synthesized` adds forward root velocity for treadmill clips (constant target speed, or stride-matched per Q4); `motion.glb` carries a root track that Godot's `AnimationPlayer` root motion reads correctly (checked with `RootMotionView`).
- **Notes:** GDD §4 stage 5.4, Q4.

### M3.3 Trim and auto-loop for cycles
- **Status:** todo
- **Depends on:** M3.2
- **Component:** pipeline
- **Effort:** M
- **Done when:** `trim` start and end frames; `auto_loop` searches a window for the pair of frames with minimum pose distance (rotations plus root velocity), crossfades N frames across the seam, and reports the loop seam error; the jog clip loops in the Gym without a visible hitch.
- **Notes:** GDD §4 stage 5.4.

### M3.4 Segmentation into named sub-clips
- **Status:** todo
- **Depends on:** M2.7
- **Component:** pipeline
- **Effort:** M
- **Done when:** a heuristic proposer (root height changes, contact changes, velocity sign changes) outputs candidate cut points with a reason each; `segments` in `meta.json` hold name, start and end; export writes one animation per segment into `motion.glb`; the vault clip splits into something like approach, vault, land.
- **Notes:** GDD §4 stage 5.5. LLM-assisted cut and name proposals come with M3.18; the heuristic stays as the default and the fallback.

### M3.5 QC report (qc.json) and thresholds
- **Status:** todo
- **Depends on:** M3.1, M3.3, M3.4
- **Component:** pipeline
- **Effort:** M
- **Done when:** `qc.json` has foot skate (cm of slide during contact), ground penetration (cm), joint jerk, loop seam error, root drift, and `betas` variance against the performer's reference; thresholds in config; an overall `status` of `ok`, `warn` or `fail`; `anim8te qc <clip_id>` prints a table; the Gym's clip list badge reads it.
- **Notes:** GDD §4 stage 5.6, goal G5.

### M3.20 Leg-swap repair and root-travel rescale
- **Status:** todo
- **Depends on:** M1.9, M3.5
- **Component:** pipeline
- **Effort:** M
- **Done when:** a clean filter detects left/right leg swaps (mesh legs out of phase with the 2D leg keypoints) and repairs them, and a travel-rescale filter scales root translation to match the hips' image-space travel at the clip's metres-per-pixel; on `vault-m05/2` and `vault-m05/3` the run-up's leg power above 6 Hz drops from 12 to 13% to under 3%, root travel lands within 10% of the image-based estimate (about 3.8 m and 3.5 m), and idle and jog clips come out unchanged; both filters are toggles in `meta.json`.
- **Notes:** Condition 3 of G0 (`docs/feasibility.md`, M0.7 vault problems and M0.9). Needs the 2D keypoints and the input video next to `hmr4d_results.pt`, so `/extract` (M1.4, M1.5) has to return them. If repair is not reliable, the fallback is a base image with her larger in frame for side-on clips.

### M3.6 clean orchestration: ordered, toggleable, re-runnable filters
- **Status:** todo
- **Depends on:** M3.5, M3.20
- **Component:** pipeline
- **Effort:** S
- **Done when:** the filter order is fixed (leg-swap repair, smooth, contacts, foot lock, ground align, travel rescale, root motion, trim and loop, segment, QC, features); each filter can be toggled and parametrised from `meta.json` or CLI flags; re-running from saved parameters is idempotent; a 5 s clip cleans in under about 10 s; `anim8te clean --explain` prints what ran and the QC deltas.
- **Notes:** This is what the Clean panel (M3.14) drives.

**Phase M3.B: the anim8te daemon**

### M3.7 anim8te daemon: FastAPI job queue and library API
- **Status:** todo
- **Depends on:** M3.6, M1.11
- **Component:** pipeline
- **Effort:** L
- **Done when:** `anim8te serve` runs on localhost; endpoints `GET /library/clips`, `GET /library/clips/{id}`, `GET /library/performers`, `POST /jobs` (gen, extract, clean, export, extend, with parameters), `GET /jobs`, `GET /jobs/{id}` (status, progress, log tail, cost), `POST /jobs/{id}/retry`, `POST /jobs/{id}/cancel`; jobs run in a background worker with state persisted (SQLite) so a restart keeps history; the CLI and the daemon call the same stage functions; an OpenAPI page is served.
- **Notes:** GDD §8. The Godot app never calls fal or the worker directly.

### M3.8 Settings and secrets
- **Status:** todo
- **Depends on:** M3.7
- **Component:** pipeline
- **Effort:** S
- **Done when:** fal key, worker URL and token, and Anthropic key are stored with `keyring` (OS keychain) with `.env` as fallback; `GET /settings` returns masked secrets; `PUT /settings` updates defaults for resolution, takes, duration and QC thresholds; secrets never appear in logs, `meta.json` or the library.
- **Notes:** GDD §7.2 Settings and §8 secrets.

**Phase M3.C: the Workflow Manager UI**

### M3.9 App shell, theme and three-pane layout
- **Status:** todo
- **Depends on:** M2.10
- **Component:** godot
- **Effort:** M
- **Done when:** top bar with Library, New Animation, Models, Jobs and Settings; left panel for Library and Models; the Gym in a centre `SubViewport`; right Inspector; bottom timeline; a custom `Theme` resource (font, colours, spacing, button and panel styles); resizable panes; all M2 Gym modes still work inside the shell.
- **Notes:** GDD §7 and §7.2 mock-up.

### M3.10 Daemon client in Godot
- **Status:** todo
- **Depends on:** M3.7, M3.9
- **Component:** godot
- **Effort:** S
- **Done when:** a `MotionAIClient` autoload wraps `HTTPRequest` for every daemon endpoint with polling and signals; connection state is shown in a status bar; the Library list comes from the daemon with the M2.5 disk scan as fallback when the daemon is down.
- **Notes:** GDD §8.

### M3.11 Library panel and Inspector
- **Status:** todo
- **Depends on:** M3.10
- **Component:** godot
- **Effort:** M
- **Done when:** the clip list shows a thumbnail (first frame of the selected take), QC badge, tags and supports search and tag filter; the Inspector shows metadata, the QC table and the filter list with current values (editable from M3.14 on); selecting a clip loads it in the Gym.
- **Notes:** GDD §7.2.

### M3.12 New Animation wizard
- **Status:** todo
- **Depends on:** M3.10
- **Component:** godot
- **Effort:** M
- **Done when:** steps for base image or performer preset, template, prompt (the template pre-fills the camera rules and shows the final prompt), takes, duration and resolution; estimated cost shown before submit; validation errors inline; submitting creates a gen job and opens the take view.
- **Notes:** GDD §7.1 Flow A steps 1 and 2.

### M3.13 Take cards and pick
- **Status:** todo
- **Depends on:** M3.12, M2.9
- **Component:** godot
- **Effort:** M
- **Done when:** takes appear as video cards as they finish, each with seed, cost and a playable preview; star to select the take; "Extract all" submits extract plus clean for every take and ranks them by QC score when done.
- **Notes:** GDD §7.1 Flow A step 3 and §4 stage 3.

### M3.14 Clean panel with live preview
- **Status:** todo
- **Depends on:** M3.11, M3.13
- **Component:** godot
- **Effort:** L
- **Done when:** filter toggles and parameters edit `meta.json` through the daemon; "Re-run" submits clean plus export and the Gym reloads `motion.glb` when done; the timeline shows contact bars, segment cuts (draggable, renamable) and QC badges; parameters changed in the UI round-trip to the CLI.
- **Notes:** GDD §7.1 Flow A step 5. Live preview means re-run then reload, not per-frame recomputation; a 5 s clip should turn around in seconds (M3.6).

### M3.15 Jobs screen
- **Status:** todo
- **Depends on:** M3.10
- **Component:** godot
- **Effort:** M
- **Done when:** a queue with job type, clip, status, progress, cost, log tail, retry and cancel; a count badge on the top bar; history survives an app restart because it comes from the daemon.
- **Notes:** GDD §7.2 Jobs.

### M3.16 Save to Library
- **Status:** todo
- **Depends on:** M3.14
- **Component:** godot
- **Effort:** S
- **Done when:** name, tags (locomotion, traversal, combat, custom), loop flag and root-motion mode are saved; the clip status becomes `ready`; it appears in the Library list with its QC badge; duplicate names are handled.
- **Notes:** GDD §7.1 Flow A step 6.

### M3.17 Flow C: Extend and chain
- **Status:** todo
- **Depends on:** M3.16
- **Component:** godot
- **Effort:** M
- **Done when:** "Extend" on a clip opens a "what happens next" prompt, calls H3 Max extend-video on the selected take through the daemon, creates a child clip linked to its parent in `meta.json`, and runs extract, clean and export on it.
- **Notes:** GDD §7.1 Flow C and §4 stage 2 extend-video (`video_url`, prompt describes what happens next).

### M3.18 Agent assist behind a toggle
- **Status:** todo
- **Depends on:** M3.14, M3.8
- **Component:** pipeline
- **Effort:** M
- **Optional:** yes
- **Done when:** with an Anthropic key set and the toggle on, the daemon offers three suggestions, each shown with Accept and Dismiss and never applied silently: a prompt written from a short intent using the template rules, segment cut points and names from per-frame features, and an explanation of a QC failure with a suggested fix.
- **Notes:** GDD §7.3. Load the `claude-api` skill when implementing; default to the latest Sonnet model and keep the prompts in `anim8te/agent/prompts/`.

### M3.19 End-to-end: a new animation from the UI
- **Status:** todo
- **Depends on:** M3.15, M3.16
- **Component:** godot
- **Effort:** S
- **Done when:** from a cold start of the daemon and the app, a new clip goes prompt, takes, pick, extract, clean, save without touching the CLI; the Jobs screen shows cost and status throughout; a capture is saved under `docs/captures/`. This closes M3.
- **Notes:** GDD §9 M3.

## M4: Workflow Manager, Flow B

**Done when:** an imported third-party humanoid plays and exports any library clip.

### M4.1 Import a model at runtime (glb, gltf, fbx)
- **Status:** todo
- **Depends on:** M3.9, M2.4
- **Component:** godot
- **Effort:** M
- **Done when:** drag-and-drop or a file dialog copies the model into `library/models/<model_id>/source.<ext>`; glTF loads with `GLTFDocument`; FBX loads with `FBXDocument` (Godot 4.3 or later) or, failing that, is converted on the daemon side; the model appears in the Models panel with a thumbnail; models with no skeleton are rejected with a clear message.
- **Notes:** GDD §7.1 Flow B step 1 and §8.1.

### M4.2 Auto bone map
- **Status:** todo
- **Depends on:** M4.1
- **Component:** godot
- **Effort:** M
- **Done when:** name-pattern heuristics (Mixamo, VRM, Unreal mannequin, Rigify, Blender defaults) plus hierarchy checks produce a `BoneMap` to `SkeletonProfileHumanoid` with a confidence per bone; unmapped and suspect bones are listed; tested on at least three free humanoid models with different naming schemes.
- **Notes:** GDD §7.1 Flow B step 2. Godot's own editor BoneMap auto-mapping logic is a useful reference for the heuristics.

### M4.3 Bone map editor UI
- **Status:** todo
- **Depends on:** M4.2
- **Component:** godot
- **Effort:** L
- **Done when:** a humanoid silhouette with a slot per profile bone (like Godot's BoneMap editor), clicking a slot assigns a bone from the model's bone list, suspect and unmapped slots are highlighted, and the map saves and loads as `library/models/<model_id>/bone_map.tres`.
- **Notes:** GDD §7.1 Flow B step 2.

### M4.4 Retarget Preview mode
- **Status:** todo
- **Depends on:** M4.3
- **Component:** godot
- **Effort:** M
- **Done when:** the mannequin and the imported model stand side by side, both driven by the same clip through `RetargetModifier3D` using the saved bone map; clip controls are shared; the starter clips show proportion differences but no broken poses.
- **Notes:** GDD §6.3 and §7.1 Flow B step 3.

### M4.5 Export baked clips onto the model's skeleton
- **Status:** todo
- **Depends on:** M4.4
- **Component:** godot
- **Effort:** M
- **Done when:** selected clips are baked onto the model's own bones and exported as `library/models/<model_id>/exports/<clip_id>.glb` with the runtime `GLTFDocument` exporter; each export re-imports in Godot and in Blender with the animation intact and the mesh still skinned.
- **Notes:** GDD §7.1 Flow B step 4, goal G3.

### M4.6 Models screen and end-to-end check
- **Status:** todo
- **Depends on:** M4.5
- **Component:** godot
- **Effort:** S
- **Done when:** the Models screen lists models with bone-map status and export history; a third-party humanoid plays and exports any library clip from the UI without the CLI; a capture is saved under `docs/captures/`. This closes M4.
- **Notes:** GDD §9 M4.

## M5: Starter set and Controller

**Done when:** about ten clips (idle, walk, jog, sprint, turn, jump, vault up, jump gap, fall, land) drive a motion-matched controller in the calibration level; the engine checkpoint is written.

### M5.1 Generate and QC the starter set
- **Status:** todo
- **Depends on:** M3.19
- **Component:** pipeline
- **Effort:** M
- **Done when:** idle, walk, jog, sprint, turn left, turn right, jump, vault up, jump gap, fall and land are all in the library with QC status `ok`; cycles are looped; root motion is set per clip; the prompts are saved as presets in the templates; any re-rolls are logged with why.
- **Notes:** GDD §9 M5. Use Flow A for everything, so the UI gets exercised.

### M5.2 Spike: Godot MotionMatching addon
- **Status:** todo
- **Depends on:** M5.1
- **Component:** godot
- **Effort:** M
- **Done when:** Q5 reviewed; Remi123/MotionMatching builds against the pinned Godot version; the starter set is indexed; `docs/motion-matching.md` records a short evaluation (transition quality, responsiveness, setup pain) and a go or fallback call (hand-built blend tree).
- **Notes:** GDD §5 and §11 addon-maturity risk. A fallback here triggers the engine checkpoint early.

### M5.3 Third-person controller
- **Status:** todo
- **Depends on:** M5.2
- **Component:** godot
- **Effort:** L
- **Done when:** WASD camera-relative movement, jump and vault on a `CharacterBody3D` in the calibration level; animation driven by motion matching over the starter set (or the blend tree fallback); root motion applied; foot placement acceptable on flat ground; the 0.5 m and 1.0 m boxes can be vaulted.
- **Notes:** GDD §6.3 Controller mode.

### M5.4 Motion-matching overlay and Controller mode
- **Status:** todo
- **Depends on:** M5.3
- **Component:** godot
- **Effort:** S
- **Done when:** Controller mode is selectable in the Gym like the other modes; an overlay shows the current motion-matching pick, its cost and the query trajectory; it toggles like the other overlays.
- **Notes:** GDD §6.4.

### M5.5 Ledge transition clips
- **Status:** todo
- **Depends on:** M5.1
- **Component:** pipeline
- **Effort:** M
- **Optional:** yes
- **Done when:** approach, grab, hang, shimmy and climb-up clips are generated and in the library with QC `ok`; the controller snaps hands to the 2.2 m ledge edge with simple IK during hang and climb.
- **Notes:** GDD §11 ledge risk. Optional for this phase; the GDD lists it as the mitigation for "lock on approach".

### M5.6 Engine checkpoint
- **Status:** todo
- **Depends on:** M5.4
- **Component:** decision
- **Effort:** S
- **Done when:** `docs/engine-checkpoint.md` re-evaluates Godot vs Unreal for the game itself against the GDD §5 criteria, with evidence from M2 to M5 (iteration speed, retargeting, motion matching quality, visual ceiling); the decision and what it changes for the next phase are written down.
- **Notes:** GDD §5 "When to revisit" and §9.

### M5.7 Spike: UniMate motion-space edits on library clips
- **Status:** todo
- **Depends on:** M5.1
- **Component:** pipeline
- **Effort:** S
- **Optional:** yes
- **Done when:** UniMate (https://huggingface.co/Linzhan/UniMate) runs on two library `motion.glb` clips (on the Mac, or the reason it cannot and what it needs instead); one in-between transition from clip A to clip B and one prompted variation of a clip (e.g. "heavy" or "tired") are exported on the canonical skeleton and judged by eye in the Gym next to their sources; `docs/unimate-spike.md` records runtime, hardware, output quality, and a go or no-go on adding a motion-space edit step after export.
- **Notes:** Text-conditioned flow-matching motion model (SIGGRAPH Asia 2026) on arbitrary rigged skeletons: in-betweening, extension, joint edits; fixed 60 frames at 30 fps. A possible cheaper route for transitions (GDD §11 ledge risk, M5.5) and variations than new H3 Max takes, not a replacement for stages 2 to 4. Checkpoints are CC BY-NC 4.0, so run it as a separate tool like GVHMR. Prompted by the author of the GDD §3.1 X thread using it to extend H3 Max-derived clips.
