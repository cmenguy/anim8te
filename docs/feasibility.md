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
