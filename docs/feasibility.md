# Feasibility test (M0.5 to M0.9)

Can one base image plus a text prompt give video that GVHMR turns into usable humanoid motion? This file logs the inputs and results of each step so the M0.9 go/no-go has the evidence in one place.

## M0.5 Generated takes (2026-10-07)

Script: `docs/scratch/feasibility_takes.py`. Base image: `library/performers/perf01/base.png` (see `library/performers/README.md`). Each take also has a JSON line in `library/clips/<clip_id>/takes/log.jsonl` with the full arguments and the fal video URL.

Common settings: model `minimax/h3-max/image-to-video`, `duration` 5, `resolution` 768P, `prompt_expansion_mode` disabled, seed = take number. Every output is 768x960 at 24 fps, 124 frames (5.17 s).

Prompts (all end in "Static camera, full body visible."; the owner asked to add "Natural movement for motion capture. Camera remains perfectly still." before it):

| Clip | Prompt |
|---|---|
| `idle-m05` | The woman stands in place on the platform, relaxed, slowly shifting her weight from one foot to the other and back, arms loose at her sides. Natural movement for motion capture. Camera remains perfectly still. Static camera, full body visible. |
| `jog-m05` | The woman jogs steadily in place on a treadmill facing the camera, at an easy, even pace with natural arm swing. Natural movement for motion capture. Camera remains perfectly still. Static camera, full body visible. |
| `vault-m05` (v1) | A waist-high grey concrete block sits on the platform just in front of her. She takes one step, places both hands on the block and vaults up onto it, landing in a crouch on top. Natural movement for motion capture. Camera remains perfectly still. Static camera, full body visible. |

| Clip | Take (seed) | File | Wall clock | Cost (list) | First look |
|---|---|---|---|---|---|
| `idle-m05` | 1 | none | | $0 | Failed: fal 403 "User is locked. Exhausted balance." |
| `idle-m05` | 2 | `takes/2.mp4` | 4.4 s | $0.15 | Subtle weight shifts, camera still, full body in frame. |
| `idle-m05` | 3 | `takes/3.mp4` | 9.8 s | $0.15 | Same; slightly more sway. |
| `jog-m05` | 1 | `takes/1.mp4` | 9.2 s | $0.15 | Jogs in place on the deck, camera still, feet visible; ponytail swings. |
| `jog-m05` | 2 | `takes/2.mp4` | 7.0 s | $0.15 | Same; clean cycle. |
| `jog-m05` | 3 | `takes/3.mp4` | 3.8 s | $0.15 | Same. |
| `vault-m05` v1 | 1 | `takes/v1/1.mp4` | 6.2 s | $0.15 | Block pops in at about 1 s; she climbs on (hands, knee) and stands up; block hides her feet; camera pushes in and shifts. |
| `vault-m05` v1 | 2 | `takes/v1/2.mp4` | 4.3 s | $0.15 | Block pops in; hands-on jump up into a crouch on top; camera mostly still. Best vault. |
| `vault-m05` v1 | 3 | `takes/v1/3.mp4` | 3.3 s | $0.15 | Block pops in; jump up, ends standing on top; camera tilts and zooms out in the last second. |

Subtotal: 8 takes, $1.20 at the $0.03/s list price measured in M0.2. Wall clock is the time `fal_client.subscribe` took for each call. Three calls ran at once.

Observations for M0.7 to M0.9:

- Idle and jog behave: the camera stays still, the whole body stays in frame and the treadmill keeps the jog in place.
- Vault v1 was the weak movement. The base image has no block, so the model makes one appear about a second in, and it ends up between the camera and her legs. What she does is a hands-on climb or jump up onto the block, not a vault over it. Takes 1 and 3 have camera motion even with the "still camera" wording. The owner asked for a redo with a side-on base image (below); the v1 takes stay under `takes/v1/` for comparison.
- The fal balance ran out during the run (idle seed 1). Each movement still has at least two takes, but the next fal task needs a top-up first.

### Vault v2: side-on base image with the block in place

The owner asked for the scene rotated 90 degrees with no treadmill: the woman on the left facing right, a long greybox block (cuboid) on the right, and room for a running jump up onto it.

Base image: `library/performers/perf01/vault/base.png` (1376x768), made from `perf01/base.png` with `fal-ai/nano-banana-pro/edit` ($0.15 per image, 16:9, 2 images per call) in three steps. Candidates and prompts are in `library/performers/perf01/vault/candidates/` (`manifest.json`):

1. `cand1`/`cand2`: re-stage side-on, no treadmill, cube on the right.
2. `cand3`/`cand4`: from `cand1`, cube replaced by a long cuboid she can stand on.
3. `cand5`/`cand6`: from `cand3`, asked for a wide shot and a 4 m run-up. The model did not zoom out (she is still about 80% of the frame height) and moved her left only about 1.75 m from the block. The owner picked `cand6`; the block's right end is cut by the frame edge.

A local composite (`comp7.png`, her and the block 4 m apart at 38% height, for a masked fill) was prepared but not used.

Prompt: "The woman runs toward the grey block, jumps, plants both hands on top of it and vaults up onto it, landing in a low crouch on top of the block. Natural movement for motion capture. Camera remains perfectly still. Static camera, full body visible." Same settings as above; outputs are 1344x768 at 24 fps, 124 frames.

| Take (seed) | File | Wall clock | Cost (list) | First look |
|---|---|---|---|---|
| 1 | `takes/1.mp4` | 6.1 s | $0.15 | Walk, hands on the block, knee up, crouch on top. More a climb than a jump. |
| 2 | `takes/2.mp4` | 5.5 s | $0.15 | Run, dive onto hands, legs swing up, crouch then rise on top. Most dynamic. |
| 3 | `takes/3.mp4` | 6.1 s | $0.15 | Run, plant hands, jump up into a crouch on top. Cleanest vault. |

In all three the body stays in frame from head to feet, because the camera follows her: it pans right during the run, so the block slides left across the frame and new set pieces (a white wall edge, light stands) come into view on the right. That ignores "Camera remains perfectly still". GVHMR estimates camera motion, so this tests that path; M0.7 to M0.9 will show whether the root trajectory survives it.

Vault v2 cost: $0.90 for the image edits (6 images) + $0.45 for the 3 takes.

**M0.5 total: $2.55 at list price** (11 video takes $1.65, image edits $0.90), under the $5 budget.

### Vault v3: wide base image (M0.11)

The v2 takes pan because she fills about 80% of the frame and runs out of it, so the video model follows her. v3 starts from a wide base image with her whole path in frame.

`comp7.png` places her and the block from `cand5` 4 m apart at 38% of the frame height on a 1376x768 canvas; `comp7_mask.png` keeps the two cut-outs (inset 6 px) and fills the rest. Both fill calls use `fal-ai/flux-pro/v1/fill` ($0.05 per megapixel, about $0.05 per image), seeds 1 and 2, PNG; prompts and URLs are in `candidates/manifest.json`.

| Call | Prompt | Result |
|---|---|---|
| 1 (`cand8`, `cand9`) | Studio wall and floor, "empty space between the woman on the left and the grey block on the right" | Both add a second block and extra women. Naming the subjects makes the fill paint copies of them. |
| 2 (`cand10`, `cand11`) | Same studio, no person or object named: "Empty room, nothing on the floor, nothing in front of the wall." | `cand10`: clean, one woman, one block, continuous wall and floor line. `cand11`: four extra people. |

The owner picked `cand10`; it is now `perf01/vault/base.png` (the v2 base was a copy of `cand6`). Fill cost: about $0.22.

Takes: same model, prompt and settings as v2 (5 s, 768P, expansion off, seeds 1 to 3), 1344x768 at 24 fps, 124 frames. The v2 takes moved to `takes/v2/`.

| Take (seed) | File | Wall clock | Cost (list) | Camera | First look |
|---|---|---|---|---|---|
| 1 | `takes/1.mp4` | 4.7 s | $0.15 | Moves: pushes in and follows her from about 2 s, ends close on her crouch | Run, hands on the block, crouch on top. Dynamic, but the push-in breaks the static assumption. |
| 2 | `takes/2.mp4` | 4.7 s | $0.15 | Still: wall seams and block fixed in every frame | Walk-run, hands on, knee up, crouch on top. A climb more than a jump. |
| 3 | `takes/3.mp4` | 4.4 s | $0.15 | Still | Same as 2, slightly lower crouch at the end. |

With her whole path in frame, two of three takes keep the camera still, against none of three in v2. She is about a third of the frame height, smaller than in the other clips; GVHMR will show whether that costs pose detail. Takes 2 and 3 can run with `-s`. Vault v3 cost: $0.22 for the fills + $0.45 for the takes.

## M0.10 GVHMR on the Mac (Apple Silicon fork)

Fork: https://github.com/ryanrudes/gvhmr at `e3876097a9c4d9c1758d058d9e70c64f0cdba4c4` (2026-07-18), cloned to `~/motion-ai-tools/gvhmr`, outside the repo. Same non-commercial GVHMR license; nothing from it is copied into `anim8te/`.

Install and run (MacBook Pro M3 Max, 48 GB, macOS 26.6):

```bash
cd ~/motion-ai-tools/gvhmr
unset VIRTUAL_ENV                     # a pyenv venv otherwise shadows the project's .venv
uv sync --frozen --extra preproc      # plain `uv sync` tries to rebuild pytorch3d from source and fails; it is only needed for an optional extra
export GVHMR_CHECKPOINTS=~/motion-ai-checkpoints GVHMR_BODY_MODELS=~/motion-ai-checkpoints/body_models
.venv/bin/gvhmr info                  # Python 3.13.5, torch 2.12.1, device MPS
.venv/bin/gvhmr demo library/clips/<clip>/takes/<n>.mp4 -s -o library/clips/<clip>/feasibility
```

`gvhmr info` reports MPS and every demo asset present from the M0.3 checkpoints. Only DPVO (CUDA-only, optional) is missing. Each output folder holds `hmr4d_results.pt` (`smpl_params_global` with `body_pose` (124, 63), `betas`, `global_orient`, `transl`) and the overlays `1_incam.mp4`, `2_global.mp4` and `<n>_3_incam_global_horiz.mp4`.

| Take | Flags | Wall time | Result |
|---|---|---|---|
| `idle-m05/2` | `-s` | 89 s | OK; includes one-time model loading |
| `idle-m05/3` | `-s` | 30 s | OK |
| `jog-m05/1` | `-s` | 30 s | OK |
| `jog-m05/2` | `-s` | 31 s | OK |
| `jog-m05/3` | `-s` | 30 s | OK |
| `vault-m05/v2/3` (panning camera) | `--camera vggt` | none | **Crashed the Mac.** The process grew to 50.2 GB on a 48 GB machine; macOS stopped responding and rebooted with a watchdog kernel panic (`panic-full-2026-10-07-011645`). Output deleted. |
| `vault-m05/2` (M0.11, still camera) | `-s` | 33 s | OK; root travels 5.1 m forward, rises 0.23 m |
| `vault-m05/3` (M0.11, still camera) | `-s` | 28 s | OK; root travels 4.6 m forward, rises 0.31 m |

GVHMR itself ("Recovered 4.1 s of motion") takes about 0.1 s per take; the rest is tracking, ViTPose, feature extraction and rendering the overlays. The overlays sit on the body in the frames checked, including the vault run-up, hands on the block and the crouch on top. M0.7 and M0.8 judge foot contact and root height properly.

Why VGGT ran out of memory: the fork runs VGGT-1B on 16 keyframes in fp32 on MPS (bf16 autocast is CUDA-only, `gvhmr/utils/preproc/vggt_slam.py:91`), and VGGT's global attention across all frames grows with the square of the token count. VGGT and DUSt3R (installed with `scripts/setup_scene_aware.sh`, 4.7 GB and 2.5 GB of weights) should not be run on this Mac at their defaults. A moving-camera take would try `--camera simplevo` (the default, rotation only, light) first.

The vault camera problem was fixed upstream of GVHMR instead: the v2 takes pan because she runs out of a tight frame; the M0.11 wide base image keeps the camera still in two of three takes, so the vault runs on the same static-camera path as idle and jog.

**Recommendation for Q2 and M0.6:** the Mac replaces the cloud GPU box for the feasibility test and for static-camera clips: about 30 s per take, no cost, no box to provision. Skip M0.6 for now and repoint M0.7 at these local outputs. Keep the cloud box as the fallback for moving-camera clips that `simplevo` cannot handle and for batch runs later; the worker's `/extract` API (GDD §8) does not care where it runs. Q2 stays open for the owner.

## M0.7 Judging the takes: motion metrics and overlays

Script: `docs/scratch/judge_takes.py`, run with the fork's venv (command in its docstring). For each take it poses the SMPL-X body from `smpl_params_global` the same way the fork's world render does: `make_smplx("supermotion")`, Y up, metres, floor at the clip's lowest vertex. It prints the table below and writes `metrics.json` and `heights.png` (pelvis, soles and foot-joint height over time) next to each take's `hmr4d_results.pt` under `library/` (git-ignored). The overlays were checked as contact sheets of 7 evenly spaced frames per take (`1_incam.mp4` above `2_global.mp4`), plus every 4th frame of the vault run-up cropped around her.

How the numbers are measured:

- **Foot slide:** horizontal movement of the `l_foot`/`r_foot` joint per frame while the foot is in contact, in cm per frame (×24 for cm/s). There are two contact labels. "Geo" means the joint is within 5 cm of its own lowest height in the clip and moving under 0.6 m/s. "GVHMR" means GVHMR's own `static_conf` head (sigmoid > 0.8), which is what its foot-locking post-process uses.
- **Jitter:** the second difference of the joint positions relative to the pelvis, in mm per frame², so travel does not count. Because fast motion also scores high on that, the table adds the share of joint-velocity power above 6 Hz: real human motion sits mostly below it and jitter does not.
- **Limb flips:** any joint whose local rotation changes by more than 45° between two frames. **Missing frames:** frame counts of the results and of all three videos.
- **Shape:** the stature of the rest-pose body from the take's `betas`.

| Take | Frames (results/input/incam/global) | Foot slide geo L/R, cm/frame (p95) | Foot slide GVHMR L/R (contact frames) | Jitter mm/f² mean / p95, power >6 Hz | Pelvis height start / min / max / end (m) | Soles end (m) | Pelvis drift (m) | Max rotation/frame | Stature (m) |
|---|---|---|---|---|---|---|---|---|---|
| `idle-m05/2` | 124/124/124/124 | 0.20 / 0.21 (0.41) | 0.20 / 0.21 (123/123) | 0.5 / 1.4, 0.9% | 0.96 / 0.95 / 0.96 / 0.95 | 0.00 | 0.13 | 1.9° | 1.70 |
| `idle-m05/3` | 124/124/124/124 | 0.33 / 0.29 (1.4) | 0.21 / 0.20 (110/98) | 0.6 / 2.1, 0.8% | 0.98 / 0.94 / 0.98 / 0.95 | 0.01 | 0.14 | 3.6° | 1.72 |
| `jog-m05/1` | 124/124/124/124 | 1.19 / 1.59 (2.3) | 1.60 / 1.73 (11/6) | 10.5 / 35.5, 0.8% | 0.98 / 0.92 / 1.01 / 0.98 | 0.02 | 0.10 | 22.6° | 1.73 |
| `jog-m05/2` | 124/124/124/124 | 1.10 / 1.11 (2.2) | 0.62 / 1.63 (8/17) | 11.9 / 40.7, 0.9% | 1.00 / 0.94 / 1.01 / 0.99 | 0.04 | 0.05 | 29.2° | 1.73 |
| `jog-m05/3` | 124/124/124/124 | 1.14 / 1.33 (2.3) | 0.99 / 1.69 (16/14) | 9.9 / 34.9, 0.9% | 0.99 / 0.95 / 1.01 / 1.00 | 0.05 | 0.09 | 22.1° | 1.73 |
| `vault-m05/2` | 124/124/124/124 | 0.87 / 0.91 (2.3) | 1.95 / 2.24 (45/13) | 10.5 / 37.4, 9.0% | 0.98 / 0.72 / 1.35 / 1.20 | 0.59 | 5.12 | 32.4° | 1.68 |
| `vault-m05/3` | 124/124/124/124 | 0.60 / 0.68 (1.4) | 2.29 / 2.00 (34/45) | 10.2 / 35.4, 9.2% | 0.99 / 0.77 / 1.43 / 1.30 | 0.72 | 4.63 | 36.5° | 1.67 |

All takes: 124 frames, 5.2 s at 24 fps. No frames are missing in the results or any overlay, mean 2D keypoint confidence never drops below 0.5 in any frame, and no joint rotates more than 45° between frames, so no hard flips show up.

### Per take

- **`idle-m05/2`, `idle-m05/3`:** clean. The overlays sit on her for the whole clip and the world view shows a relaxed stand with small weight shifts. Jitter is under 1 mm/frame². The feet are in contact in every frame but creep about 0.2 to 0.3 cm/frame (5 to 8 cm/s), back and forth: net foot displacement over the clip is 5 cm in take 2 and 15 cm in take 3. The pelvis wanders 13 to 14 cm. A foot lock in cleanup has to remove this, or an idle loop will visibly skate.
- **`jog-m05/1` to `/3`:** good. She jogs in place, so the treadmill belt does not drag the feet, and the overlays follow the arm swing and knee lift in every sheet frame. Treadmill drift is 5 to 10 cm over 5.2 s (1 to 2 cm/s), and the pelvis bobs about 5 cm per step, so root motion has to be added in cleanup, as planned. Feet lift 10 to 15 cm. During contact the feet slide 1.1 to 1.6 cm/frame (26 to 38 cm/s), which will show as skating. GVHMR's own contact head fires on only 2 to 17 frames per foot, against 21 to 34 by the geometric rule, so its foot-locking post-process barely acts on the jog. Cleanup needs its own contact detection. Jitter is high in mm/frame² only because the motion is fast: power above 6 Hz is under 1%, the same as idle.
- **`vault-m05/2`, `vault-m05/3`:** the motion reads correctly: walk-run in, plant both hands on the block, jump up, crouch on top. **Height is right.** In the first frame of the input video the block's front face is 115 to 123 px tall against her 377 px (head to sole) at about the same depth, so the block is about 0.53 m (×1.68 m stature). The GVHMR soles go from 0.05 m to 0.60 m in take 2 (+0.55) and from 0.13 m to 0.72 m in take 3 (+0.59). The +0.23 and +0.31 m "rise" in M0.10 was `transl`, which follows the pelvis into a crouch, not the feet. The prompt's "waist-high" block came out knee-high.
- **Vault problems:**
  1. *Leg swaps in the run-up.* Seen side-on, the legs cross, and in several frames (take 2 around frames 40 and 56, take 3 around frames 24, 28 and 60) the mesh legs are out of phase with her real legs, which show in black beside the mesh. That is where the 9% of power above 6 Hz comes from: it is 12 to 13% in the first 2.5 s and 1 to 2% after landing. These are left/right swaps, not single-frame flips, so the 45° check does not catch them.
  2. *Travel is overestimated.* GVHMR moves the pelvis 5.1 m and 4.6 m. Her hips move 850 px and 795 px in the image, about 3.8 m and 3.5 m at the same px-per-metre scale, so the world trajectory comes out about 30 to 35% too long.
  3. *The floor tilts in take 3.* The soles climb from 0.06 m to about 0.15 m during the run-up before the jump, so GVHMR's ground is tilted about 2° along her path.

### Body shape across takes

`betas` are constant within each take (GVHMR averages the per-frame estimates, whose spread is 0.08 to 0.31). Statures: idle 1.70 and 1.72, jog 1.73 for all three, vault 1.68 and 1.67. The 6 cm spread between movements follows how large she is in frame: the vault, where she is a third of the frame height, comes out shortest and its `betas` differ most. Pipeline consequence: a performer's clips should share one body shape, picked once per performer, rather than taking each clip's own.

### What this means for M0.9

- Idle and jog are usable after cleanup: foot locking, root motion for the jog, and light smoothing. No missing frames and no flips.
- The vault is usable for its height and its key poses (hands on the block, the crouch on top). Its run-up has left/right leg swaps and about 30% too much travel, so it needs either cleanup that detects swaps and rescales root travel, or a base image where she is larger in frame.

## M0.9 Go/no-go (2026-10-07)

**Decision: go, with conditions.** The owner made the call on the M0.7 evidence above. GVHMR on H3 Max video is good enough to build the pipeline on; stages 2 (video) and 4 (extraction) stay as designed.

Evidence:

- GVHMR runs on the Mac (Apple-Silicon fork) in about 30 s per still-camera take, at no cost (M0.10).
- Idle and jog: no missing frames, no flips over 45°, high-frequency power under 1%; overlays track arm swing and knee lift. Remaining faults are the ones stage 5 cleanup is designed for: foot creep (idle 5 to 8 cm/s, jog 26 to 38 cm/s during contact), treadmill drift of 5 to 10 cm, and GVHMR's own contact head firing on too few frames.
- Vault: key poses and height are right (soles rise 0.55 to 0.59 m for a block of about 0.53 m). The run-up has left/right leg swaps (9% power above 6 Hz), travel about 30 to 35% too long, and in one take a floor tilted about 2°.
- Stature varies 1.67 to 1.73 m across clips of the same performer.

Conditions, and where each one lives in the plan:

1. Cleanup does its own contact detection and foot locking rather than relying on GVHMR's contact head: M2.7 (contacts in `features.json`) and M3.1 (foot lock).
2. One body shape per performer, chosen once and reused by every clip, rather than each clip's own `betas`: M1.8 (Notes) and M3.5 (`betas` variance in QC).
3. Dynamic clips with side-on run-ups get leg-swap repair and root-travel rescaling, or a base image where she is larger in frame: new task M3.20.
4. The Mac worker takes still-camera clips only. Moving-camera takes are flagged, not run through VGGT or DUSt3R at their defaults (that crashed the Mac in M0.10); they go to a cloud box or are avoided through framing: M1.4 (Notes).
