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
- Open the PR, report the link, and ask the owner whether to merge it now; merge (`gh pr merge <n> --squash --delete-branch`) only on a yes. After a merge, `git checkout main && git pull --ff-only` before anything else.
- Never commit `.env`, `library/`, body models or checkpoints. `.gitignore` already covers them.

## Layout (GDD §8.2)

```
GDD.md  PLAN.md  README.md  CLAUDE.md
.claude/skills/   next-step, roadmap (and the plan parser)
godot/            Godot 4.x project: Gym + Workflow Manager         (from M2)
anim8te/          Python package: CLI, pipeline stages, daemon      (from M1)
worker/           gvhmr-worker around GVHMR (Mac fork), own uv project (from M1.4)
library/          performers, clips, models; git-ignored
tests/            pytest; fixtures stay under 1 MB
docs/             feasibility, pipeline notes, findings, captures
```

Since M0.1 every directory exists with a one-line README; the annotations above say which milestone fills it in. `library/` is git-ignored except `library/README.md`. `.env.example` lists the secret names.

## Conventions

- Python 3.11 or later, `uv`, `typer` CLI, `pydantic` models, `pytest`, `ruff`. Settings resolve in this order: `--library`, environment, `.env`, `~/.config/anim8te/config.toml` (non-secret keys only: `library`, `gvhmr_worker_url`), then `./library`. Stage code under `anim8te/stages/` has no CLI or HTTP concerns, so the CLI, the daemon and the tests share it.
- GVHMR output (`hmr4d_results.pt`) is always 30 fps: the demo resamples the input, whatever the take's rate. `anim8te.convert` reads `smpl_params_global` and finds the SMPL-X model at `$GVHMR_BODY_MODELS` (default `~/motion-ai-checkpoints/body_models`), the same variable the worker uses.
- Axes: GVHMR's world frame is Y-up, right-handed, metres, with +Z pointing away from the video camera. `anim8te.convert.to_gltf_frame()` turns it 180° about Y, so a performer facing the camera faces +Z, the glTF front. Convert world points and `global_orient`, never SMPL-X `transl`. Details in `docs/pipeline-notes.md`.
- `anim8te clean` always starts from the raw `gvhmr/` output, so re-runs are idempotent. Filter toggles and parameters live in `meta.json` `filters` (defaults written back on every run). `clean/motion.npz` is the canonical-skeleton motion in the glTF frame (local rotations as x, y, z, w quaternions, Hips translation) that `anim8te export` reads (it also stores the rest sole height, `sole_y`). Ground alignment puts the soles, not the joints, at y = 0, using each foot joint's rest height above the lowest SMPL-X vertex. Every clean also writes `features.json` (`ClipFeatures` in `anim8te/library.py`: per-frame foot and toe contacts, root position and velocity, joint positions, joint jerk, and the foot joints' rest heights above the soles), which the Gym overlays and QC read instead of recomputing. Contact thresholds are the `contacts` filter; speed is measured against the ground velocity, estimated automatically so treadmill belts count as ground (`docs/pipeline-notes.md` M2.7).
- Godot 4.7 (Q7; `RetargetModifier3D` needs 4.4 or later), pinned in `godot/project.godot`. One unit is one metre, Y-up, right-handed.
- Canonical skeleton: Godot `SkeletonProfileHumanoid` bone names on the 22 SMPL-X body joints (table in GDD §4 stage 5). Every library clip is a `motion.glb` on that skeleton; the mannequin and imported models are retargeted from it. The default mannequin is Quaternius Universal Base Characters (Q1) under `godot/assets/mannequin/`, imported with a `BoneMap` on that profile, bones renamed, unique `%GeneralSkeleton`, Overwrite Axis and fix silhouette (details in `godot/README.md`).
- `motion.glb` is skeleton only (no mesh): an `Armature` root, the 22 canonical bones with identity rest rotations, the rest pose standing on y = 0 and the Spine to Head offsets straightened to vertical (M2.12; keeps the humanoid retarget from hunching), one skin, one animation named after the clip id (Hips translation plus every bone's rotation, LINEAR, one key per frame).
- Library layout per GDD §8.1: `library/clips/<id>/` holds `meta.json`, `takes/`, `selected.mp4` (and `selected.ogv`), `gvhmr/` (with `overlay.ogv`), `clean/motion.npz`, `motion.glb`, `qc.json`, `features.json`. The `meta.json` and `qc.json` schemas are the pydantic models in `anim8te/library.py`; clip ids are `<slug>-<6 random chars>`. A performer's body shape is `library/performers/<id>/betas.json`, set by its first clip and reused by every later one (`anim8te.skeleton.performer_betas`).
- Prompts for video generation end with "Static camera, full body visible." Cyclic locomotion is generated "on a treadmill"; root motion is added in cleanup. The rules live in `anim8te/templates/*.toml` (one per template); `anim8te gen` applies them, and the UI and agent assist read the same files.
- The Godot app loads library clips at runtime with `ClipPlayer` (`godot/scripts/clip_player.gd`): `GLTFDocument`, the clip re-expressed on the driven model's rest, then `RetargetModifier3D` (humanoid profile, local pose) with the model's `Skeleton3D` as its direct child. Gotchas in `godot/README.md` "Runtime retargeting". The Gym's clip list is `LibraryPanel` over `LibraryScanner` (disk scan of `library/clips/*/`), and `ClipViewer` plays its selection through `ClipPlayer`'s transport (play/pause, seek, step, speed, loop); `CompareView` (M2.10, toggled from the bar) shows the take, the 3D clip and the GVHMR overlay with the videos following the `ClipPlayer`'s clock (sync notes in `godot/README.md` "Compare"); the library root is `--library=<path>` after `--`, else `ANIM8TE_LIBRARY`, else `<repo>/library`.
- The playable grey box (M2.13) is `scenes/greybox_play.tscn`: `GreyboxPlayer` (`godot/scripts/greybox_player.gd`), a `CharacterBody3D` with an `AnimationTree` built in code over the editor-imported clips in `godot/assets/sample_clips/` (idle, walk, jog in a speed blend space, the vault as a one-shot with its horizontal travel applied to the body), and `FollowCamera`. Details in `godot/README.md` "Playable grey box".
- The Gym's debug overlays (M2.8) are `DebugOverlay` nodes under `ClipOverlays` (`Character/Overlays`), one per overlay, all drawn from the clip's `features.json` in the ClipPlayer's space; their on/off state persists in `user://gym_settings.cfg`. Details in `godot/README.md` "Debug overlays".
- Godot 4 plays only Ogg Theora (Q6): `anim8te extract` also writes `selected.ogv` and `gvhmr/overlay.ogv` (`anim8te/video.py`; video only, same size, rate and frame count, checked with ffprobe), and `anim8te transcode` does it for older clips. The mp4 files stay the source of truth. It needs an ffmpeg with libtheora: Homebrew's `ffmpeg` has none, so `brew install ffmpeg-full` (keg-only, found automatically) or `ANIM8TE_FFMPEG`.
- The Godot app never calls fal or the GPU worker directly. It talks to the local `anim8te` daemon over HTTP and loads `.glb` files from the library.
- Secrets (`FAL_KEY`, `GVHMR_WORKER_TOKEN`, `ANTHROPIC_API_KEY`) live in `.env` or the OS keychain, never in the library, logs or git. `.env.example` lists the names.
- Anything calling Anthropic models (agent assist, M3.18) goes through the `claude-api` skill.

## Licensing guardrails

- GVHMR and SMPL-X are non-commercial research licenses. This is a prototype. Stage 4 stays behind the worker's `/extract` API so a licensed or commercial service can replace it.
- ComfyUI-MotionCapture is GPL-3.0: read it for reference, run it as a separate service, never copy its code into `anim8te/`.
- The mannequin and any bundled asset must be CC0 or similarly permissive, with the license file stored next to the asset.

## Commands

```bash
python3 .claude/skills/next-step/scripts/plan.py next        # what to work on
python3 .claude/skills/next-step/scripts/plan.py summary     # progress
python3 .claude/skills/next-step/scripts/plan.py check       # validate PLAN.md
uv sync                                                     # install anim8te and dev tools into .venv
uv run pytest                                               # tests
uv run ruff check . && uv run ruff format --check .         # lint
uv run anim8te --library <path> lib path                    # resolved library root
uv run anim8te lib ls                                       # clips and performers with status
uv run anim8te gen --performer perf01 --template locomotion --prompt "..." --dry-run  # final prompt + cost, no fal call
uv run anim8te extract <clip_id> [--take n]                 # stage 4 through gvhmr-worker -> gvhmr/ + .ogv copies, status extracted
uv run anim8te transcode <clip_id>                          # selected.ogv + gvhmr/overlay.ogv for clips extracted before M2.9
uv run anim8te clean <clip_id> [--no-smooth] [--set smooth.window=11]  # smoothing + ground + contacts -> clean/motion.npz, features.json, status cleaned
uv run anim8te export <clip_id>                             # clean/motion.npz -> motion.glb (skeleton, skin, one animation), status exported
anim8te serve                                               # local daemon for the Godot app (M3.7)
godot --editor --path godot                                 # open the Godot project (main scene: scenes/main.tscn)
godot --headless --path godot --script tests/check_runtime_retarget.gd  # runtime GLB + RetargetModifier3D vs the clip (M2.4)
godot --headless --path godot --script tests/check_library_scanner.gd   # library scan + clip list panel on a fixture library (M2.5)
godot --headless --path godot --script tests/check_clip_viewer.gd       # Clip Viewer transport, follow camera, clip switching (M2.6)
godot --headless --path godot --script tests/check_overlays.gd          # debug overlays vs features.json, toggle persistence (M2.8)
godot --headless --path godot --script tests/check_video_playback.gd    # VideoStreamPlayer plays a clip's .ogv files (M2.9)
godot --path godot --script tests/check_compare.gd                      # Compare mode sync: drift, speed, loop, scrub; on-screen frames vs ffmpeg (M2.10; --headless skips the screen part)
godot --path godot scenes/greybox_play.tscn                            # playable grey box: WASD, Shift jog, E vault (M2.13)
godot --headless --path godot --script tests/check_greybox.gd           # grey-box controller: movement, blend speeds, collision, vault onto the block (M2.13)
worker/setup.sh                                             # install GVHMR (pinned Mac fork) + the worker
uv run --project worker gvhmr-worker                        # GVHMR worker on 127.0.0.1:8765 (API in worker/README.md)
cd worker && uv run pytest                                  # worker tests (fake gvhmr CLI)
```

## Keeping the docs current

When a task changes the layout, the commands or a convention, update README.md and this file in the same change. The plan's Notes lines point at GDD sections; keep those pointers valid if the GDD is renumbered.
