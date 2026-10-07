"""M0.2 throwaway: one 5 s, 768P H3 Max image-to-video clip from a full-body image.

Usage (from the repo root, FAL_KEY in .env):

    .venv/bin/python docs/scratch/fal_smoke_test.py --image path/to/full_body.png
    .venv/bin/python docs/scratch/fal_smoke_test.py --gen-image   # no image at hand

--gen-image first makes a placeholder full-body image with a cheap fal text-to-image
model. Output goes to library/scratch/m0.2/ (git-ignored). Not part of motionai/.
"""

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "library" / "scratch" / "m0.2"

I2V_MODEL = "minimax/h3-max/image-to-video"
T2I_MODEL = "fal-ai/flux/schnell"
PROMPT = "The man takes three slow steps forward, then stops. Static camera, full body visible."
IMAGE_PROMPT = (
    "Full-body photo of an adult man in a plain grey t-shirt, dark trousers and sneakers, "
    "standing in a neutral A-pose, entire body from head to feet in frame, "
    "plain light studio background, even lighting, front view."
)
PRICE_PER_S_768P = 0.08  # GDD §4 stage 2 list price; confirm on the fal billing page


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        f.write(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", type=Path, help="full-body base image")
    src.add_argument("--gen-image", action="store_true", help="generate a placeholder base image")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("FAL_KEY is not set; add it to .env (https://fal.ai/dashboard/keys)")
    import fal_client  # reads FAL_KEY from the environment

    OUT.mkdir(parents=True, exist_ok=True)

    if args.gen_image:
        r = fal_client.subscribe(T2I_MODEL, arguments={
            "prompt": IMAGE_PROMPT,
            "image_size": "portrait_16_9",
            "num_images": 1,
            "seed": args.seed,
        })
        image_url = r["images"][0]["url"]
        download(image_url, OUT / "base.png")
        print(f"base image: {OUT / 'base.png'}")
    else:
        image_url = fal_client.upload_file(str(args.image))

    arguments = {
        "image_url": image_url,
        "prompt": PROMPT,
        "duration": 5,
        "resolution": "768P",
        "seed": args.seed,
        "prompt_expansion_mode": "disabled",
    }
    t0 = time.monotonic()
    r = fal_client.subscribe(I2V_MODEL, arguments=arguments, with_logs=True)
    elapsed = time.monotonic() - t0

    mp4 = OUT / f"h3max_768p_5s_seed{args.seed}.mp4"
    download(r["video"]["url"], mp4)

    report = {
        "model": I2V_MODEL,
        "arguments": {k: v for k, v in arguments.items() if k != "image_url"},
        "video_url": r["video"]["url"],
        "mp4": str(mp4.relative_to(ROOT)),
        "mp4_bytes": mp4.stat().st_size,
        "wall_clock_s": round(elapsed, 1),
        "list_price_usd": round(5 * PRICE_PER_S_768P, 2),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
