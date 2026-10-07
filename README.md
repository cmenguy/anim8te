# Motion AI

An experiment in making game animations with AI instead of a mocap suit. One base image plus a text prompt becomes a short video, the video becomes 3D motion, and the motion lands in an engine-agnostic library on a canonical humanoid skeleton that any character can play.

```
base image -> AI video per movement -> 3D motion extraction -> cleanup -> canonical skeleton -> any character
```

**Status:** October 2026. M0 (feasibility, go/no-go) passed; M1 builds the pipeline CLI. The `anim8te` package installs; `anim8te gen` generates takes on fal (M1.3), and the other pipeline commands are stubs until their M1 tasks land.

## What is being built

- **Pipeline** (`anim8te`, Python): fal H3 Max for video, GVHMR for motion extraction on a rented CUDA GPU, our own cleanup (smoothing, foot locking, root motion, auto-loop, segmentation, quality checks), glTF export.
- **The Gym** (Godot 4): a metric calibration level and a default mannequin, with clip playback, debug overlays (foot contacts, root trajectory, jitter), side-by-side comparison with the source video, retarget preview, and a motion-matched test controller.
- **The Workflow Manager** (Godot 4, same app): add a new animation from a prompt in a few clicks; import a humanoid model, map its bones once, then play or export any library clip on it.

The final game is out of scope. The output of this project is the pipeline and the animation library a game can be built on.

## Documents

| File | What it is |
|---|---|
| [GDD.md](GDD.md) | Design document: goals, pipeline stages, engine choice, Gym, Workflow Manager, architecture, milestones, licensing, risks |
| [PLAN.md](PLAN.md) | Build plan: milestones M0 to M5 broken into tasks with dependencies, status, effort and acceptance criteria |
| [CLAUDE.md](CLAUDE.md) | Working conventions for Claude Code sessions in this repo |

## Working the plan

PLAN.md is the source of truth for what to do next and what is done. Two Claude Code skills in `.claude/skills/` drive it:

- `/next-step` picks the next task (dependencies and milestone order), starts it, and records the result with a dated log line.
- `/roadmap` prints a progress summary, whole plan or one milestone.

Every task is done on its own branch (`task/<id>-<few-words>`) and lands on `main` through a pull request; `main` is protected and nothing is pushed to it directly. The repository lives at https://github.com/cmenguy/anim8te.

The same information is available without Claude:

```bash
python3 .claude/skills/next-step/scripts/plan.py summary
python3 .claude/skills/next-step/scripts/plan.py next
python3 .claude/skills/next-step/scripts/plan.py set M0.2 done --note "cost was $0.41 per take"
python3 .claude/skills/next-step/scripts/plan.py check
```

## Milestones

| # | Milestone | Proves |
|---|---|---|
| M0 | Accounts, GPU box, feasibility test | GVHMR output on H3 Max video is usable. Go/no-go gate |
| M1 | Pipeline CLI, one clip | `gen`, `extract`, `clean`, `export` turn one prompt into a `motion.glb` that plays in Godot |
| M2 | Gym: Clip Viewer and Compare | Library clips play on the mannequin with overlays, frame-synced to the source video |
| M3 | Workflow Manager, Flow A | A new animation goes from prompt to library entirely from the UI |
| M4 | Workflow Manager, Flow B | An imported third-party humanoid plays and exports any library clip |
| M5 | Starter set and Controller | About ten clips drive a motion-matched controller; engine checkpoint |

## Prerequisites

Collected as the plan progresses; none are needed to read the documents.

- A Mac for development with Python 3.11 or later and Godot 4.7 (`brew install --cask godot`).
- A fal.ai account and API key for video generation (about $0.40 per 5-second take at 768p).
- SMPL-X and SMPL research licenses, for the body models GVHMR and the converter use. The converter reads `SMPLX_NEUTRAL.npz` from `$GVHMR_BODY_MODELS/smplx/` (default `~/motion-ai-checkpoints/body_models`, see `docs/checkpoints.md`); tests that need it skip when it is missing.
- An Apple Silicon Mac with 32 GB or more for GVHMR, through the fork at https://github.com/ryanrudes/gvhmr (`worker/setup.sh` installs it; see `worker/README.md`). A cloud NVIDIA GPU is only needed later, for moving-camera clips or batch runs.
- ffmpeg (`brew install ffmpeg`): GVHMR needs its `ffprobe` to read frame rates. Writing the Ogg Theora copies Godot plays needs a build with libtheora, which Homebrew's `ffmpeg` lacks: `brew install ffmpeg-full` (keg-only, installs beside it; `anim8te` finds it, or set `ANIM8TE_FFMPEG`).
- Optional: an Anthropic API key for the agent-assist features.

Install the package and dev tools with [uv](https://docs.astral.sh/uv/) (`pip install -e .` also works):

```bash
uv sync
uv run anim8te --help
uv run pytest
```

The GVHMR worker is a separate uv project under `worker/`: `worker/setup.sh` installs it and GVHMR, `uv run --project worker gvhmr-worker` starts it on `127.0.0.1:8765`, and `worker/README.md` documents the API.

The library root defaults to `./library`; override it with `--library`, `ANIM8TE_LIBRARY`, or `library = "..."` in `~/.config/anim8te/config.toml`.

Secrets go in `.env` (names listed in `.env.example`), never in git; `.gitignore` already excludes `.env`, `.envrc`, the library and all model checkpoints.

GitHub access uses the personal `cmenguy` login through a git-ignored `.envrc` loaded by [direnv](https://direnv.net/):

```bash
cat > .envrc <<'EOF'
export GH_TOKEN=$(gh auth token --hostname github.com --user cmenguy)
dotenv_if_exists .env
EOF
direnv allow .
```

Shells without direnv (Claude Code's tool shell, for one) prefix `gh` and `git push` with `GH_TOKEN=$(gh auth token --hostname github.com --user cmenguy)`.

## Repository layout

```
GDD.md  PLAN.md  README.md  CLAUDE.md
.claude/skills/   next-step and roadmap skills, plan parser
godot/            Godot project: Gym + Workflow Manager
anim8te/         Python package: CLI, pipeline stages, local daemon
worker/           gvhmr-worker: FastAPI wrapper around GVHMR (Mac fork now, GPU box later), setup.sh
library/          performers, clips and models on disk (git-ignored)
tests/            pipeline unit tests (axis conventions, bone map, QC metrics)
docs/             feasibility notes, pipeline notes, findings, captures
```

Each directory holds a one-line README until its milestone fills it in. `library/` is git-ignored apart from its README. Copy `.env.example` to `.env` for the secrets.

## Licensing

GVHMR and the SMPL-X body models are licensed for non-commercial research, so everything here is a prototype. The extraction stage sits behind a small worker API so it can be swapped for a licensed or commercial service before any release. ComfyUI-MotionCapture (GPL-3.0) is used only as a separate test bench. Details and the commercial path are in GDD §10.

## Credits

The pipeline approach follows the @MrCollison thread of October 2026 (GDD §3). Motion extraction is [GVHMR](https://github.com/zju3dv/GVHMR) (SIGGRAPH Asia 2024). Video generation is [H3 Max on fal](https://fal.ai/models/minimax/h3-max/image-to-video).
