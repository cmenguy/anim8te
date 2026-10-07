#!/usr/bin/env bash
# Install GVHMR (Apple-Silicon fork, pinned) and the worker's own environment.
#
# The checkpoints are not downloaded here: they are mounted or copied in once (M0.3) and the
# worker reads them from $GVHMR_CHECKPOINTS (body models from $GVHMR_BODY_MODELS, default
# $GVHMR_CHECKPOINTS/body_models). GVHMR and SMPL-X are non-commercial research licenses.
#
#   GVHMR_HOME         where the fork is cloned        (default ~/motion-ai-tools/gvhmr)
#   GVHMR_CHECKPOINTS  mounted checkpoint directory    (default ~/motion-ai-checkpoints)
#   GVHMR_BODY_MODELS  SMPL/SMPL-X body models         (default $GVHMR_CHECKPOINTS/body_models)
set -euo pipefail

GVHMR_REPO=https://github.com/ryanrudes/gvhmr
GVHMR_COMMIT=e3876097a9c4d9c1758d058d9e70c64f0cdba4c4
GVHMR_HOME=${GVHMR_HOME:-$HOME/motion-ai-tools/gvhmr}
GVHMR_CHECKPOINTS=${GVHMR_CHECKPOINTS:-$HOME/motion-ai-checkpoints}
GVHMR_BODY_MODELS=${GVHMR_BODY_MODELS:-$GVHMR_CHECKPOINTS/body_models}
WORKER_DIR=$(cd "$(dirname "$0")" && pwd)

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
command -v ffprobe >/dev/null || {
  # GVHMR reads the frame rate with ffprobe and silently assumes 30 fps without it, so 24 fps
  # takes would skip resampling and come out 25% fast.
  echo "ffprobe is required: brew install ffmpeg (or apt install ffmpeg)" >&2
  exit 1
}
unset VIRTUAL_ENV # a pyenv venv otherwise shadows the project's .venv

for dir in "$GVHMR_CHECKPOINTS" "$GVHMR_BODY_MODELS"; do
  [[ -d $dir ]] || { echo "missing $dir: mount or copy the M0.3 checkpoints first" >&2; exit 1; }
done

if [[ ! -d $GVHMR_HOME/.git ]]; then
  git clone "$GVHMR_REPO" "$GVHMR_HOME"
fi
git -C "$GVHMR_HOME" fetch --quiet origin
git -C "$GVHMR_HOME" checkout --quiet "$GVHMR_COMMIT"

# Plain `uv sync` tries to build pytorch3d from source and fails; it is only needed for an extra.
(cd "$GVHMR_HOME" && uv sync --frozen --extra preproc)

GVHMR_CHECKPOINTS=$GVHMR_CHECKPOINTS GVHMR_BODY_MODELS=$GVHMR_BODY_MODELS \
  "$GVHMR_HOME/.venv/bin/gvhmr" info

(cd "$WORKER_DIR" && uv sync)

echo
echo "Installed. Start the worker with:"
echo "  GVHMR_BIN=$GVHMR_HOME/.venv/bin/gvhmr GVHMR_CHECKPOINTS=$GVHMR_CHECKPOINTS \\"
echo "    uv run --project $WORKER_DIR gvhmr-worker"
