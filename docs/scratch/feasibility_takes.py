"""M0.5 throwaway: the feasibility takes (idle, jog, vault) from perf01's base images.

Usage (from the repo root, FAL_KEY in .env):

    .venv/bin/python docs/scratch/feasibility_takes.py                # all clips, seeds 1-3
    .venv/bin/python docs/scratch/feasibility_takes.py --clip vault-m05 --seeds 4

Takes land in library/clips/<clip_id>/takes/<n>.mp4 (git-ignored); each run appends
one JSON line per take to library/clips/<clip_id>/takes/log.jsonl. Existing takes are
skipped, so a re-run only fills gaps. Not part of anim8te/.
"""

import argparse
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BASE_IMAGE = ROOT / "library" / "performers" / "perf01" / "base.png"
CLIPS = ROOT / "library" / "clips"

I2V_MODEL = "minimax/h3-max/image-to-video"
PRICE_PER_S_768P = 0.03  # fal pricing API, 2026-10-06 (M0.2)
SUFFIX = "Natural movement for motion capture. Camera remains perfectly still. Static camera, full body visible."
PROMPTS = {
    "idle-m05": (
        "The woman stands in place on the platform, relaxed, slowly shifting her weight from one "
        "foot to the other and back, arms loose at her sides. " + SUFFIX
    ),
    "jog-m05": (
        "The woman jogs steadily in place on a treadmill facing the camera, at an easy, even pace "
        "with natural arm swing. " + SUFFIX
    ),
    # v2: side-on base image with the block already in it; v1 (block in front, invented by the
    # video model) is kept under takes/v1/ and in docs/feasibility.md.
    "vault-m05": (
        "The woman runs toward the grey block, jumps, plants both hands on top of it and vaults up "
        "onto it, landing in a low crouch on top of the block. " + SUFFIX
    ),
}
BASE_IMAGES = {"vault-m05": ROOT / "library" / "performers" / "perf01" / "vault" / "base.png"}


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        f.write(r.read())


def take(fal_client, image_url: str, base: Path, clip_id: str, seed: int, duration: int) -> dict:
    out = CLIPS / clip_id / "takes" / f"{seed}.mp4"
    if out.exists():
        return {"clip_id": clip_id, "seed": seed, "skipped": True}
    arguments = {
        "image_url": image_url,
        "prompt": PROMPTS[clip_id],
        "duration": duration,
        "resolution": "768P",
        "seed": seed,
        "prompt_expansion_mode": "disabled",
    }
    t0 = time.monotonic()
    r = fal_client.subscribe(I2V_MODEL, arguments=arguments)
    elapsed = time.monotonic() - t0
    out.parent.mkdir(parents=True, exist_ok=True)
    download(r["video"]["url"], out)
    rec = {
        "clip_id": clip_id,
        "take": seed,
        "model": I2V_MODEL,
        "arguments": {k: v for k, v in arguments.items() if k != "image_url"},
        "base_image": str(base.relative_to(ROOT)),
        "video_url": r["video"]["url"],
        "mp4": str(out.relative_to(ROOT)),
        "mp4_bytes": out.stat().st_size,
        "wall_clock_s": round(elapsed, 1),
        "list_price_usd": round(duration * PRICE_PER_S_768P, 2),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(out.parent / "log.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", choices=sorted(PROMPTS), action="append", help="default: all")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--duration", type=int, default=5)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("FAL_KEY is not set; add it to .env (https://fal.ai/dashboard/keys)")
    import fal_client

    clips = args.clip or sorted(PROMPTS)
    bases = {c: BASE_IMAGES.get(c, BASE_IMAGE) for c in clips}
    urls = {b: fal_client.upload_file(str(b)) for b in set(bases.values())}
    jobs = [(c, s) for c in clips for s in args.seeds]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(take, fal_client, urls[bases[c]], bases[c], c, s, args.duration)
            for c, s in jobs
        ]
        for (clip_id, seed), fut in zip(jobs, futures):
            try:
                print(json.dumps(fut.result()))
            except Exception as e:  # keep the other takes going
                print(json.dumps({"clip_id": clip_id, "seed": seed, "error": repr(e)}))


if __name__ == "__main__":
    main()
