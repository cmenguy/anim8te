# worker

gvhmr-worker: a small FastAPI service that takes a video and returns GVHMR's `hmr4d_results.pt` and an overlay video (GDD §8). It runs GVHMR's demo CLI as a subprocess, one job at a time, and never imports GVHMR. On the Mac that CLI is the Apple-Silicon fork (`gvhmr demo <video> -s`, MPS; Q2, `docs/feasibility.md` M0.10). A CUDA box can take over later without changing the API.

The worker is its own uv project (`worker/pyproject.toml`), separate from `anim8te`. GVHMR and SMPL-X are non-commercial research licenses. Stage 4 stays behind this API so a licensed or commercial service can replace it. There is no GPL code here.

## Install

```bash
worker/setup.sh
```

`setup.sh` does four things:

1. Clones the fork at the pinned commit into `$GVHMR_HOME` (default `~/motion-ai-tools/gvhmr`).
2. Runs `uv sync --frozen --extra preproc` there.
3. Runs `gvhmr info` against the checkpoints.
4. Installs the worker's own environment.

It needs `uv` and `ffprobe` (`brew install ffmpeg`). Without `ffprobe`, GVHMR assumes 30 fps, skips resampling 24 fps takes and recovers them 25% fast.

The checkpoints are not downloaded. They are the M0.3 set, mounted or copied in once:

| Variable | Default | What |
|---|---|---|
| `GVHMR_CHECKPOINTS` | `~/motion-ai-checkpoints` | gvhmr, hmr2, vitpose, yolo checkpoints |
| `GVHMR_BODY_MODELS` | `$GVHMR_CHECKPOINTS/body_models` | SMPL / SMPL-X (registration-gated) |

## Start

```bash
uv run --project worker gvhmr-worker      # from the repo root, so ./.env is read
curl http://127.0.0.1:8765/health
```

The worker reads its settings from the environment, then from `./.env`:

| Variable | Default | What |
|---|---|---|
| `GVHMR_WORKER_TOKEN` | required | bearer token; `anim8te` sends the same value |
| `GVHMR_BIN` | `~/motion-ai-tools/gvhmr/.venv/bin/gvhmr` | the GVHMR demo CLI |
| `GVHMR_WORKER_DATA` | `~/.cache/gvhmr-worker/jobs` | one folder per job: input, log, results |
| `GVHMR_WORKER_HOST` / `_PORT` | `127.0.0.1` / `8765` | bind address; use `0.0.0.0` on a remote box |
| `GVHMR_WORKER_TIMEOUT` | `1800` | seconds before a GVHMR run is killed |

Jobs run one at a time, because MPS memory does not survive two GVHMR processes at once. Finished jobs survive a restart. A job that was queued or running when the worker stopped comes back as `failed`.

## API

Every route except `/health` needs `Authorization: Bearer $GVHMR_WORKER_TOKEN`; without it the worker returns `401`.

**`POST /extract`**: multipart form with `video` (an `.mp4`) and `static_camera` (default `true`). It returns `202 {"job_id": "...", "status": "queued"}`. The worker refuses these requests with `422`:

- A non-`.mp4` or empty upload.
- `static_camera=false`. The Mac worker runs still-camera takes only (G0). Moving-camera backends (VGGT, DUSt3R) ran the Mac out of memory in M0.10, so those takes go to a CUDA box or are avoided through framing.

```bash
curl -H "Authorization: Bearer $GVHMR_WORKER_TOKEN" \
  -F video=@library/clips/<clip>/takes/1.mp4 -F static_camera=true \
  http://127.0.0.1:8765/extract
```

**`GET /jobs/{id}`**: returns the status, which is one of `queued`, `running`, `done` or `failed`. The response also includes `error`, the last 40 lines of the GVHMR log (`log_tail`) and timestamps. When the job is `done`, `files` holds the download URLs:

```json
{"job_id": "71726b616b42", "status": "done", "error": null, "log_tail": ["..."],
 "files": {"hmr4d_results.pt": "http://127.0.0.1:8765/jobs/71726b616b42/files/hmr4d_results.pt",
           "overlay.mp4": "http://127.0.0.1:8765/jobs/71726b616b42/files/overlay.mp4"}}
```

**`GET /jobs/{id}/files/{name}`**: downloads `hmr4d_results.pt` or `overlay.mp4`. It returns `409` while the job is not `done`. `overlay.mp4` is GVHMR's side-by-side in-camera and world render (`<stem>_3_incam_global_horiz.mp4`).

**`GET /health`**: no token needed. Reports whether the GVHMR CLI, the checkpoints, the body models and `ffprobe` are present, and how many jobs are pending.

## Tests

```bash
cd worker && uv run pytest
```

The tests use a fake `gvhmr` script that writes the same files the real demo writes, so they run without GVHMR or a GPU.
