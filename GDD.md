# Motion AI: Game Design Document

| | |
|---|---|
| **Project** | Motion AI (working title) |
| **Owner** | Charles Menguy |
| **Status** | Draft v0.1 |
| **Date** | 2026-10-06 |
| **Engine** | Godot 4.x (see [section 5](#5-engine-decision-godot-vs-unreal)) |

---

## 1. Overview

Motion AI is a tool-first prototype for a modern, Tomb Raider-style third-person action game. The final game will need a large library of movement animations (locomotion, vaulting, climbing, ledge work, combat). Instead of a mocap suit or stock Mixamo clips, Motion AI makes those animations with AI:

```
base image -> AI video per movement -> 3D motion extraction -> cleanup -> canonical skeleton -> any character
```

This project covers the **foundation** only:

1. **The Gym.** A simple 3D test level with a default humanoid skeleton, where any animation in the library can be previewed, inspected and driven by a basic controller.
2. **The Workflow Manager.** A polished UI that turns the pipeline into a few clicks. It makes it easy to (a) **add new animations** from a prompt and base image, and (b) **apply existing animations to a different 3D model** through retargeting.

The game itself (level design, combat, narrative) is out of scope here. The output of this project is the animation pipeline and library the game will be built on.

## 2. Goals and non-goals

### Goals

- G1. Generate a new, usable animation clip from a text prompt and base image in about **20 minutes** with **no manual 3D work** in the happy path.
- G2. Keep every animation in an **engine-agnostic library** (glTF on a canonical humanoid skeleton), so it can later move to Unreal or another engine.
- G3. Import an arbitrary humanoid model (glTF/FBX), map its bones once, and **play or export any library clip on it**.
- G4. Give a **gym** to judge quality: clip playback, foot-contact and trajectory overlays, side-by-side with the source video, and a simple motion-matched controller.
- G5. Flag quality problems automatically (foot skate, ground penetration, jitter) so bad takes are rejected early, before cleanup time is spent on them.

### Non-goals (this phase)

- Shipping game content, levels, combat systems or story.
- Hand/finger animation (the extraction model doesn't estimate fingers; see [section 11](#11-risks-and-open-questions)).
- Facial animation.
- Non-humanoid skeletons (quadrupeds, creatures).
- Commercial release of anything built on non-commercial components (see [section 10](#10-licensing)).

## 3. Background research

### 3.1 Source: the @MrCollison thread (Oct 2026)

Matt (@MrCollison, CTO at MSQ Intelligence) posted a working version of this pipeline on X.

- **Main post** ([link](https://x.com/MrCollison/status/2107214135188656510), Oct 5 2026): "These are not Mixamo animations. These are neurally motion-matched animations from 9 x H3 Max (@fal) videos (8 x image-to-video, 1 x extend-video)", bundled in a three.js WebGPU playground with custom IK and blending. Video two shows the references: one actor in black, static camera, grey studio, with clips labelled idle / jog / sprint.
- **Quoted post** ([link](https://x.com/MrCollison/status/2106858957352374607), Oct 4 2026): a one-shot sword-combat test using H3 Max image-to-video as the reference, with a coding agent ("Astra", OpenAI's GPT-6 Astra at xhigh effort) building the matching.

Details from the replies:

| Topic | What he said |
|---|---|
| Motion extraction model | "GHVMR [sic, GVHMR] is the best model by a country mile. Grab the SMPL-X rig (after accepting terms) and you're off to the races." |
| Agent effort | Built "within 3 prompts (4 if you include me asking for ACES + SSGI)", from videos to demo. |
| Clip segmentation | For parkour, Opus 5.5 extracted 3 clips from one video: vault up, jump gap, fall. |
| Procedural editing | "Everything is procedurally modified so longer jumps, though naive, look normal." |
| Turnaround | "A new set of animations takes about 20 mins including vid gen & gait matching." Low token cost. |
| Model choice | "With this method you'd get the same results with Opus 4.6." The method matters more than the model. |
| Video prompts | "Very basic", single reference image; he picked the second of two outputs. |
| Known gaps | Needs more animation states; ledge jumps "lock you on approach". Commenters flagged weak sword arcs and hands. Foot-contact stability on the vault was asked about and not answered. |
| Next | A demo link and a "free open source parkour player controller" were promised for the week of Oct 5 2026. |

### 3.2 Takeaways for this project

- The video model is a **stand-in for a mocap suit**. Video quality and camera discipline decide everything downstream.
- The hard parts are **after** extraction: foot contact, root motion, segmentation, retargeting and transitions. The Workflow Manager should spend most of its effort here.
- Motion matching hides a lot of per-clip imperfection, and a gym with debug overlays is the fastest way to see what still breaks.
- An LLM agent is useful **inside** the pipeline (choosing segment cut points, naming clips, writing prompts), not only for writing the code.

## 4. The animation pipeline

Six stages. Each one is a job in the Workflow Manager ([section 7](#7-the-workflow-manager)) with its own inputs, outputs and status.

```
[1 Base image] -> [2 Generate video] -> [3 Pick take] -> [4 Extract motion] -> [5 Convert + clean] -> [6 Library]
                       fal H3 Max          human/agent      GVHMR (CUDA GPU)     SMPL-X -> humanoid      glTF clips
                                                                                                          |
                                                                       [Gym preview] <-------------------+
                                                                       [Retarget to model X] <-----------+
```

### Stage 1: Base image

One image of the performer, reused for every movement so all clips share the same body proportions.

- Full body in frame, head to feet, with margin on all sides.
- Locked-off camera at roughly waist height, facing the subject.
- Plain background, one person, fitted clothing (no capes or long coats hiding limbs).

### Stage 2: Generate video (fal H3 Max)

- Image-to-video: https://fal.ai/models/minimax/h3-max/image-to-video (model `minimax/h3-max/image-to-video`)
- Extend-video: https://fal.ai/models/minimax/h3-max/extend-video (model `minimax/h3-max/extend-video`)
- API key: https://fal.ai/dashboard/keys

Key inputs for image-to-video: `image_url`, `prompt`, `duration` (0.92 to 15 s, default 5), `resolution` (`480P` / `768P` / `1080P`), `seed`, `prompt_expansion_mode` (`disabled` / `balanced` / `quality`). Output: `video.url`.

```python
import fal_client  # pip install fal-client; export FAL_KEY=...

img = fal_client.upload_file("base.png")
r = fal_client.subscribe("minimax/h3-max/image-to-video", arguments={
    "image_url": img,
    "prompt": "The woman vaults up onto a waist-high concrete block. Static camera, full body visible.",
    "duration": 5,
    "resolution": "768P",
    "prompt_expansion_mode": "disabled",  # keep the prompt literal
})
print(r["video"]["url"])
```

Extend-video takes `video_url` (1.625 to 60 s, up to 50 MB) and a `prompt` describing **what happens next**, not the source.

Prompting rules (prompt templates live in the Workflow Manager):

- Always end with "Static camera, full body visible."
- Cyclic locomotion (walk, jog, sprint): "on a treadmill" keeps the subject in frame and gives clean loops. Root motion is added later in stage 5.
- One action per clip. Chain actions with extend-video instead of packing them into one prompt.
- Generate 2 to 3 takes per movement with different seeds.

Cost: about $0.05/s at 480p, $0.08/s at 768p, $0.16/s at 1080p, so roughly $0.40 per 5-second take at 768p. Measured in M0.2 (2026-10-06): fal lists H3 Max image-to-video at $0.03/s, so a 5-second 768p take cost $0.15.

### Stage 3: Pick take

The user (or an agent ranking by QC score from stage 5) picks the best take. The Workflow Manager shows takes side by side and can run a fast extraction preview on all of them.

### Stage 4: Extract motion (GVHMR)

- Repo: https://github.com/zju3dv/GVHMR
- Install guide: https://github.com/zju3dv/GVHMR/blob/main/docs/INSTALL.md
- Paper: https://arxiv.org/abs/2409.06662 (SIGGRAPH Asia 2024)
- **Requires an NVIDIA GPU with CUDA.** It won't run on the dev Mac, so it runs on a rented cloud GPU (RunPod / Lambda / similar) behind a small worker API.

Setup:

```bash
git clone https://github.com/zju3dv/GVHMR && cd GVHMR
conda create -y -n gvhmr python=3.10 && conda activate gvhmr
pip install -r requirements.txt && pip install -e .
mkdir -p inputs/checkpoints outputs
```

Checkpoints:

```
inputs/checkpoints/
├── body_models/smplx/SMPLX_{NEUTRAL,MALE,FEMALE}.npz   # https://smpl-x.is.tue.mpg.de/ (sign up, accept license)
├── body_models/smpl/SMPL_{...}.pkl                    # https://smpl.is.tue.mpg.de/
├── gvhmr/gvhmr_siga24_release.ckpt                    # Google Drive link in INSTALL.md
├── hmr2/epoch=10-step=25000.ckpt
├── vitpose/vitpose-h-multi-coco.pth
└── yolo/yolov8x.pt
```

Run (`-s` = static camera, which skips visual odometry; this is why stage 1 demands a locked-off camera):

```bash
python tools/demo/demo.py --video=clips/vault.mp4 -s
python tools/demo/demo_folder.py -f clips -d outputs/demo -s   # batch
```

Output: `outputs/demo/<clip>/hmr4d_results.pt`, a torch dict. We use `smpl_params_global` (per-frame `global_orient`, `body_pose`, `transl`, `betas`). GVHMR also renders overlay videos, which the Workflow Manager shows next to the source.

#### Alternative: ComfyUI-MotionCapture

[ComfyUI-MotionCapture](https://github.com/PozzettiAndrea/ComfyUI-MotionCapture) (GPL-3.0) is a ComfyUI node pack that wraps the same GVHMR model. It covers stage 4 and part of stage 5:

| Our stage | Covered by ComfyUI-MotionCapture |
|---|---|
| 2. Generate video | No |
| 4. Extract motion | Yes: `GVHMR Inference` (static and moving camera) |
| 5. Convert | Partly: `SMPL to BVH`, `SMPL to GLB Animation`, `SMPL to FBX`, `SMPL to Mixamo` |
| 5. Cleanup (foot lock, smoothing, loop, root motion) and segmentation | No |
| Retarget | Yes, through headless Blender (`bpy`), with bone maps for Mixamo and VRM |
| Preview | Basic SMPL / BVH / FBX viewers and skeleton comparison inside ComfyUI |
| Library, QC, Godot, motion matching | No |

How we use it:

1. **M0 feasibility test bench.** Run the first H3 Max takes through its bundled `workflows/GVHMR.json`, export GLB, and inspect the result in Godot before writing any pipeline code. This answers the key question early: is GVHMR on AI-generated video good enough?
2. **Reference code** for SMPL to BVH/GLB conversion and joint naming. Read it, don't copy it: copying GPL-3.0 code into `anim8te` would make that package GPL.
3. **Optional `gvhmr-worker` backend.** ComfyUI exposes a workflow API, so the GPU box can run ComfyUI with this pack instead of our own GVHMR wrapper (see [section 8](#8-technical-architecture)).

It does not replace the Workflow Manager or the stage 5 cleanup, and it doesn't change licensing: it still runs GVHMR and SMPL-X under their non-commercial terms. It also needs an NVIDIA CUDA GPU, and its one-click installer is marked experimental (manual install is the reliable path).

### Stage 5: Convert and clean

This is our own code (Python package `anim8te`). The steps:

1. **Load** `smpl_params_global`; rebuild SMPL-X joint positions from `betas` with the `smplx` Python package.
2. **Axis fix.** Convert to glTF/Godot conventions (Y-up, right-handed, meters). Verify GVHMR's world-frame up axis on the first clip and lock it in with a unit test.
3. **Map to the canonical skeleton.** Map the 22 SMPL-X body joints to Godot's `SkeletonProfileHumanoid` names (see the table below). Fingers are left at rest pose.
4. **Cleanup filters** (each one can be toggled in the UI):
   - Temporal smoothing (One-Euro or Savitzky-Golay) to remove jitter.
   - Foot-contact detection (foot height plus velocity thresholds), then **foot locking** with two-bone IK during contacts.
   - Ground alignment, so the lowest contact sits at y = 0.
   - Root motion: extract it from the hips, or for treadmill clips **synthesize** forward root velocity from the target speed.
   - Trim, plus **auto-loop** for cycles (find the best loop seam by pose distance and crossfade it).
5. **Segment.** Split a long clip into named sub-clips (vault_up / jump_gap / fall). An LLM agent proposes cut points from per-frame features (root height, contacts, velocity) and the user confirms them on a timeline.
6. **QC report** (`qc.json`): foot skate (cm of foot slide during contact), ground penetration, joint jerk, loop seam error, root drift. Clips over thresholds are flagged red.
7. **Export** `motion.glb`: canonical skeleton plus one animation per sub-clip.

Initial SMPL-X to `SkeletonProfileHumanoid` map:

| SMPL-X | Humanoid | SMPL-X | Humanoid |
|---|---|---|---|
| pelvis | Hips | left_hip / right_hip | LeftUpperLeg / RightUpperLeg |
| spine1 | Spine | left_knee / right_knee | LeftLowerLeg / RightLowerLeg |
| spine2 | Chest | left_ankle / right_ankle | LeftFoot / RightFoot |
| spine3 | UpperChest | left_foot / right_foot | LeftToes / RightToes |
| neck | Neck | left_collar / right_collar | LeftShoulder / RightShoulder |
| head | Head | left_shoulder / right_shoulder | LeftUpperArm / RightUpperArm |
| | | left_elbow / right_elbow | LeftLowerArm / RightLowerArm |
| | | left_wrist / right_wrist | LeftHand / RightHand |

### Stage 6: Library

Clips land in the library on the canonical skeleton. From there they can be previewed in the Gym, retargeted onto any imported model, or exported.

## 5. Engine decision: Godot vs Unreal

### Recommendation: Godot 4.x for this project; keep Unreal open for the final game.

| Criterion | Godot 4.x | Unreal Engine 5 |
|---|---|---|
| Fit for "gym + workflow tool" | Strong. The editor is built on its own UI toolkit, so polished tool UIs are easy to build | Possible (Editor Utility Widgets, Python), but heavier and more awkward for a standalone tool |
| Runtime retargeting | Built in: `SkeletonProfileHumanoid` + `BoneMap` at import, and `RetargetModifier3D` (4.4+) at runtime | Built in: IK Retargeter (editor-time, very mature) |
| Motion matching | Community GDExtension ([Remi123/MotionMatching](https://github.com/Remi123/MotionMatching), Godot 4.4+, still in development) | First-party, production-grade (Pose Search) plus Epic's free Game Animation Sample Project |
| Iteration speed on a Mac | Fast: ~100 MB editor, opens instantly, hot reload | Slow: tens of GB, long compiles and shader builds, Mac is a second-tier platform |
| Scripting | GDScript (Python-like) / C#; easy to shell out to the Python pipeline | C++ / Blueprints; editor Python only |
| Visual ceiling for a "modern" AAA look | Good, not AAA | Best available (Lumen, Nanite, MetaHuman) |
| License | MIT, free | Free until revenue threshold, then royalty |
| glTF support | First-class (native format) | Good (import plugin) |

**Why Godot now.** This phase builds a **tool and a test gym**, not the shipped game. What matters is fast iteration, an easy custom UI, runtime retargeting, and running well on the Mac. Godot wins on all four. Its glTF-native pipeline also matches our library format exactly.

**Why Unreal later, maybe.** A *modern* Tomb Raider-style game benefits from Unreal's rendering and its production-grade motion matching. Because the library is engine-agnostic glTF on a standard humanoid skeleton (G2), moving the **content** to Unreal later is a retarget and import, not a rewrite. Only the Gym and Workflow Manager UI are Godot-specific, and they stay useful as an authoring tool even if the game ships on Unreal.

**When to revisit.** At the end of milestone M5 ([section 9](#9-milestones)), or sooner if the Godot motion-matching addon can't give acceptable locomotion in the Gym.

## 6. The Gym

A single Godot scene for judging animation quality, not for gameplay.

### 6.1 Level layout (grey-box, metric)

- 40 x 40 m ground plane with a 1 m grid and 10 cm sub-grid.
- **Calibration props** sized to standard parkour metrics: boxes at 0.5 / 1.0 / 1.5 m (step, vault, climb-up), a 2.2 m ledge wall (hang / climb), gaps of 1.5 / 2.5 / 3.5 m between platforms, a 20° and a 35° ramp, a staircase (0.18 m risers), and a 0.3 m beam.
- A neutral HDRI and directional light, ACES tone mapping. Looks are not the goal, but readable silhouettes are.

### 6.2 Default character

- **Skeleton:** Godot `SkeletonProfileHumanoid`, the canonical skeleton for the whole library.
- **Mesh:** a neutral, CC0-licensed mannequin rigged to that profile (candidate: a Quaternius CC0 humanoid; see open question Q1). Using the SMPL-X mesh for the gym is avoided for licensing reasons.

### 6.3 Modes

| Mode | Purpose |
|---|---|
| **Clip Viewer** | Play any library clip on the default character. Timeline scrub, speed control, loop toggle, frame stepping. |
| **Compare** | Split view: source video, GVHMR overlay video, and the 3D clip, all frame-synced. This reproduces the "references in video two" view from the thread. |
| **Retarget Preview** | Default character and an imported model side by side, both driven by the same clip through `RetargetModifier3D`. |
| **Controller** | Third-person WASD + jump/vault controller, motion-matched over the library, to test transitions in the calibration level. |

### 6.4 Debug overlays (toggle per overlay)

Foot-contact markers (green planted / red sliding), root trajectory (past and predicted), velocity vectors, ground-penetration highlight, skeleton wireframe, joint-jerk heatmap, and the current motion-matching pick and cost.

## 7. The Workflow Manager

The main product surface: a polished desktop UI built in Godot (Control nodes with a custom theme) **in the same app as the Gym**. The Gym is the 3D viewport panel; the Workflow Manager is everything around it.

### 7.1 Core flows

**Flow A: Add a new animation**

1. **New Animation**: pick a base image (or a performer preset), pick a template (Locomotion cycle / Traversal / Combat / Custom), enter a prompt (template pre-fills the camera rules), choose takes (default 3), duration and resolution.
2. **Generate**: takes appear as video cards while they render; each card shows cost and seed.
3. **Pick**: star the best take, or press "Extract all" to rank takes by QC score.
4. **Extract**: send to the GPU worker; shows a progress bar and queue position.
5. **Clean**: the cleanup panel shows each filter with a toggle and parameters, plus a timeline with contact bars, suggested segment cuts and the QC badges. Changes preview live in the Gym.
6. **Save to Library**: name, tags (locomotion / traversal / combat), loop flag, root-motion mode.

**Flow B: Apply existing animations to a new model**

1. **Import Model**: drag in a `.glb` / `.gltf` / `.fbx` humanoid.
2. **Bone Map**: the model's bones are auto-mapped to `SkeletonProfileHumanoid` and shown on a humanoid silhouette, like Godot's own BoneMap editor; unmapped or suspect bones are highlighted for manual fixes. Saved per model.
3. **Preview**: pick clips and play them on the new model in Retarget Preview mode.
4. **Export**: bake the selected clips onto the model's own skeleton and export `.glb` (with Godot's runtime `GLTFDocument`), for use in Godot, Unreal, Blender or elsewhere.

**Flow C: Extend / chain**

From any clip, "Extend" calls H3 Max extend-video with a "what happens next" prompt (e.g. after vault_up: "she drops down and rolls"), then re-runs stages 4 to 6.

### 7.2 Screens

```
+----------------------------------------------------------------------------------+
|  MOTION AI    [Library] [New Animation] [Models] [Jobs (2)]          [Settings]  |
+-------------------+------------------------------------------+-------------------+
| LIBRARY           |                                          | INSPECTOR         |
| search / tags     |            GYM VIEWPORT (3D)             | clip: vault_up    |
|  > idle      [ok] |                                          | QC: foot skate 1cm|
|  > jog       [ok] |                                          |     jerk ok       |
|  > vault_up  [!]  |                                          | filters:          |
|  > jump_gap  [ok] |                                          |  [x] smooth  0.4  |
|  > sword_1   [x]  |                                          |  [x] foot lock    |
|                   |                                          |  [ ] auto-loop    |
| MODELS            |                                          | [Re-run] [Extend] |
|  > mannequin *    +------------------------------------------+ [Export...]       |
|  > lara_v2        | TIMELINE  |--cut--|------cut------|  contacts ▬▬ ▬▬ ▬▬   |
+-------------------+------------------------------------------+-------------------+
```

- **Library**: clip list with thumbnails, QC badge, tags and search.
- **New Animation**: the flow A wizard.
- **Models**: imported models and their bone maps (flow B).
- **Jobs**: queue of generation and extraction jobs with status, logs, cost and retry.
- **Settings**: fal API key, GPU worker URL and token, default resolution and takes, QC thresholds.

### 7.3 Agent assist (optional, behind a toggle)

An LLM (Claude via the Anthropic API) is used for three narrow jobs, each shown to the user as a suggestion, never applied silently:

- Write prompts from a short intent ("parkour vault, athletic woman") using the template rules.
- Propose segment cut points and names from per-frame features (the Opus vault / jump / fall split in the thread).
- Explain QC failures and suggest the fix, e.g. "re-roll: feet leave frame at 3.2 s".

## 8. Technical architecture

```
+---------------------- Dev machine (Mac) -----------------------+      +---- Cloud GPU ----+
|                                                                |      |                   |
|  Godot app: Gym + Workflow Manager                             |      |  gvhmr-worker     |
|      |  HTTP (localhost)                                       |      |  FastAPI + GVHMR  |
|      v                                                         | HTTPS|  POST /extract    |
|  anim8te daemon (Python, FastAPI)  ---------------------------------->|  GET  /jobs/{id}  |
|      |-- fal_client --------------------> fal.ai (H3 Max)       |      +-------------------+
|      |-- convert / clean / QC (numpy, smplx, scipy, pygltflib)  |
|      |-- Anthropic API (agent assist, optional)                 |
|      v                                                         |
|  library/ (files on disk, git-LFS-friendly)                    |
+----------------------------------------------------------------+
```

- **Godot app** owns the UI and 3D preview and never calls external services directly. It talks to the local daemon over HTTP and loads `.glb` files from the library at runtime.
- **`anim8te` daemon** (Python) owns the job queue, fal calls, conversion, cleanup, QC and the library on disk. It also runs as a CLI (`anim8te gen|extract|clean|export`) so every stage can be scripted and tested without the UI.
- **`gvhmr-worker`** runs on a CUDA box. It takes a video and returns `hmr4d_results.pt` (or equivalent SMPL params) and the overlay video. Two interchangeable backends behind the same `/extract` API:
  - **Native (default):** a thin FastAPI wrapper around GVHMR's `tools/demo/demo.py`. Fewest dependencies, no GPL code.
  - **ComfyUI:** ComfyUI with [ComfyUI-MotionCapture](https://github.com/PozzettiAndrea/ComfyUI-MotionCapture), driven through ComfyUI's workflow API. Faster to stand up for M0 and comes with viewers for debugging. Run it as a separate service so its GPL-3.0 code stays out of `anim8te`.
- **Secrets** (fal key, worker token, Anthropic key) live in the OS keychain or `.env`, never in the library or git.

### 8.1 Library layout

```
library/
├── performers/<performer_id>/
│   ├── base.png
│   └── betas.json         # SMPL-X body shape, fixed by the performer's first clip
├── clips/<clip_id>/
│   ├── meta.json          # name, tags, prompt, seed, take ids, filters, loop, root-motion mode
│   ├── takes/<n>.mp4      # all generated takes
│   ├── selected.mp4
│   ├── gvhmr/hmr4d_results.pt + overlay.mp4
│   ├── motion.glb         # canonical skeleton + sub-clip animations
│   └── qc.json
└── models/<model_id>/
    ├── source.glb|fbx
    ├── bone_map.tres      # Godot BoneMap -> SkeletonProfileHumanoid
    └── exports/<clip_id>.glb
```

### 8.2 Repository layout (proposed)

```
motion-ai/
├── GDD.md
├── godot/            # Godot project: Gym + Workflow Manager
├── anim8te/          # Python package: daemon + CLI + pipeline stages
├── worker/           # gvhmr-worker (Dockerfile + FastAPI)
├── library/          # git-ignored or git-LFS
└── tests/            # pipeline unit tests (axis conventions, bone map, QC metrics)
```

## 9. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Accounts, GPU box, feasibility test | fal key works; ComfyUI + ComfyUI-MotionCapture runs on the cloud GPU; 3 to 5 H3 Max takes (idle, jog, vault) go through its `GVHMR.json` workflow to GLB and are judged by eye in Godot. **Go/no-go:** if GVHMR output on AI video is unusable, stop and rethink stages 2 and 4 before building anything else |
| M1 | Pipeline CLI, one clip | `anim8te gen && extract && clean && export` turns one prompt into `motion.glb` that imports into Godot on the humanoid profile |
| M2 | Gym: Clip Viewer + Compare | Library clips play on the default mannequin with overlays; Compare view is frame-synced to source video |
| M3 | Workflow Manager: Flow A | A new animation goes from prompt to library entirely from the UI; Jobs screen shows cost and status |
| M4 | Workflow Manager: Flow B | An imported third-party humanoid plays and exports any library clip |
| M5 | Starter set + Controller | ~10 clips (idle, walk, jog, sprint, turn, jump, vault up, jump gap, fall, land) driving a motion-matched controller in the calibration level |
| — | Engine checkpoint | Re-evaluate Godot vs Unreal for the game itself ([section 5](#5-engine-decision-godot-vs-unreal)) |

## 10. Licensing

| Component | License | Implication |
|---|---|---|
| GVHMR | "Educational, research and non-profit purposes only"; derivatives must be open-source and non-commercial; commercial use by request to the authors (email in [LICENSE](https://github.com/zju3dv/GVHMR/blob/main/LICENSE)) | Prototype only unless a commercial license is obtained |
| SMPL / SMPL-X body models | Non-commercial research license; commercial licensing via Meshcapade | Same: fine for prototyping, not for shipping |
| fal / H3 Max outputs | fal terms of service | Check commercial-use terms before shipping |
| ComfyUI-MotionCapture | GPL-3.0 (plus the GVHMR and SMPL terms it inherits) | Use as a separate service or as reading material; don't copy its code into `anim8te` |
| Godot | MIT | No restrictions |
| Default mannequin | Must be CC0 or similarly permissive | Pick accordingly (Q1) |

**Commercial path.** Before any commercial release, either license GVHMR and SMPL-X, or swap stage 4 for a commercial video-to-mocap service (e.g. Move.ai, Rokoko Video, DeepMotion), which usually return FBX directly. Keep stage 4 behind the `/extract` worker interface so the swap is a backend change only.

## 11. Risks and open questions

### Risks

| Risk | Mitigation |
|---|---|
| GVHMR output on AI-generated video is too noisy to use | Test first in M0 with ComfyUI-MotionCapture before building the pipeline; go/no-go gate |
| Foot skate and contact errors on dynamic moves (vaults, landings) | Foot-lock IK in stage 5; QC thresholds; re-roll takes instead of hand-fixing |
| No fingers or prop contact (weak sword arcs and hands, as commenters noted) | Out of scope now; later, hand poses from a dedicated hand model or hand-keyed overlays |
| Ledge / climb transitions "lock on approach" | Generate explicit transition clips (approach, grab, hang, shimmy, climb up) and add procedural IK to ledge edges in the Controller |
| Video-model identity or proportion drift between takes | One base image per performer; QC check on `betas` variance across clips |
| Godot motion-matching addon immature | Fall back to a hand-built blend tree for M5; this triggers the engine checkpoint |
| Non-commercial dependencies leak into the game | Licensing table above; stage 4 behind a swappable interface |

### Open questions

- **Q1.** Which CC0 mannequin becomes the default character?
- **Q2.** Which GPU host for `gvhmr-worker` (always-on vs spin-up per batch)?
- **Q3.** Performer: one generic base image, or a Lara-like character from day one?
- **Q4.** Root-motion policy for treadmill loops: synthesized constant speed, or speed-matched to the stride length?
- **Q5.** Does the @MrCollison open-source parkour controller (promised Oct 2026) change the Controller plan?

## 12. References

### Source thread
- Main post: https://x.com/MrCollison/status/2107214135188656510
- Quoted post: https://x.com/MrCollison/status/2106858957352374607

### Video generation (fal)
- H3 Max announcement: https://fal.ai/learn/devs/introducing-h3-max-by-fal
- H3 Max image-to-video: https://fal.ai/models/minimax/h3-max/image-to-video (API summary: https://fal.ai/models/minimax/h3-max/image-to-video/llms.txt)
- H3 Max extend-video: https://fal.ai/models/minimax/h3-max/extend-video
- API keys: https://fal.ai/dashboard/keys

### Motion extraction
- GVHMR repo: https://github.com/zju3dv/GVHMR
- GVHMR install: https://github.com/zju3dv/GVHMR/blob/main/docs/INSTALL.md
- GVHMR paper: https://arxiv.org/abs/2409.06662
- SMPL-X: https://smpl-x.is.tue.mpg.de/
- SMPL: https://smpl.is.tue.mpg.de/
- ComfyUI-MotionCapture (GVHMR as ComfyUI nodes; M0 test bench and optional worker backend): https://github.com/PozzettiAndrea/ComfyUI-MotionCapture (example workflow: `workflows/GVHMR.json`)

### Godot
- Retargeting 3D skeletons: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/retargeting_3d_skeletons.html
- `RetargetModifier3D`: https://docs.godotengine.org/en/stable/classes/class_retargetmodifier3d.html
- `BoneMap`: https://docs.godotengine.org/en/stable/classes/class_bonemap.html
- Godot Motion Matching (GDExtension): https://github.com/Remi123/MotionMatching (Asset Library: https://godotengine.org/asset-library/asset/3822)

### Unreal (for the engine checkpoint)
- Motion Matching in Unreal Engine: https://dev.epicgames.com/documentation/en-us/unreal-engine/motion-matching-in-unreal-engine
- Game Animation Sample Project (free, on Fab)
