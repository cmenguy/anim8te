# Pipeline notes

Findings about the pipeline stages that the code depends on. Each section names the task that established it.

## Axis conventions: GVHMR world frame to glTF (M1.7)

**Finding.** `smpl_params_global` is in GVHMR's "ay" world frame, which is Y-up, right-handed and in metres. glTF uses the same axes and units. The two frames differ only in heading:

| Axis | GVHMR world ("ay") | glTF / Godot (ours) |
|---|---|---|
| +Y | up (minus gravity) | up |
| +Z | camera viewing direction on frame 0, projected onto the ground (away from the camera) | asset front (towards the video camera) |
| +X | camera-left | camera-right (screen right) |

**Source.** In `gvhmr/utils/geo/hmr_global.py` of the pinned fork, `get_R_c2gv` builds the gravity-view frame from the camera's frame: y is gravity (down), x is gravity × camera z (camera-right) and z is the camera's horizontal view direction. `gvhmr_pipeline.py` then applies `tsf="any->ay"`, a 180° turn about Z that flips y and x. The result is y up, x camera-left, z away from the camera. Both steps are proper rotations, so there is no mirroring.

**Conversion.** `anim8te.convert.to_gltf_frame()` turns the frame 180° about Y, using `GVHMR_TO_GLTF = diag(-1, 1, -1)`, which is a rotation (det +1):

- World points (joint positions, the pelvis track) become `R @ p`.
- The pelvis world rotation `global_orient` becomes `R @ R_go`.
- Parent-relative rotations (`body_pose`) are unchanged.
- SMPL-X `transl` is not a point. The model applies it on top of the pelvis rest position and rotates about that position, so a frame change has to go through the posed pelvis position, not through `transl`.

After the conversion, a performer facing the camera faces +Z, the glTF front. In GVHMR's frame that performer has a 180° yaw; in ours the pelvis rotation is the identity. A Godot camera at +Z looking down -Z (Camera3D's default direction) frames the clip the way the video does, with screen right at +X.

**Verified on real clips** (posed with the SMPL-X neutral model, then converted):

| Clip | Frames | Head above pelvis | Lowest foot joint y (min / median) | Facing on frame 0 | Video |
|---|---|---|---|---|---|
| walk-ur7zdb (treadmill) | 155 | 0.60 m | 0.113 / 0.123 m | +Z (0.98 or more on every frame) | faces the camera |
| idle-m05 takes 2, 3 | 124 | 0.59 to 0.61 m | -0.025 to -0.002 m | +Z | faces the camera |
| jog-m05 takes 1 to 3 | 124 | 0.60 m | -0.009 to 0.066 m | +Z (0.96 or more) | faces the camera |
| vault-m05 takes 2, 3 | 124 | 0.40 to 0.45 m (crouching) | 0.12 to 0.26 m | +X | runs to screen right; pelvis travels +4.6 to +5.1 m in X |

- **Up.** The head is above the pelvis and the feet are lowest on every frame of every clip.
- **Handedness.** Left-hip minus right-hip crossed with pelvis-to-head (left × up) points the same way as the toes; a mirrored frame would flip one of the two. On every frame of the walk, idle and jog clips, the horizontal cosine between the two is 0.95 or more. On the vault, the median cosine is 0.73 to 0.82. The low frames are the crouch on the box, where pelvis-to-head is far from vertical.
- **Forward.** Clips that face the camera face +Z. The vault faces and travels +X, which is screen right for a camera at +Z, and that is what the video shows.

**What the conversion does not do.** GVHMR's floor is not at y = 0. The walk clip's lowest foot joint sits 11 to 14 cm up and the vault's 12 cm or more. The SMPL-X `*_foot` joint is at the ball of the foot, a few cm above the sole. Ground alignment is a cleanup filter (GDD §4 stage 5.4; `anim8te clean`, M1.9: on the walk clip it lowers the body 8.9 cm so the 5th-percentile sole height is 0), as is turning a clip's heading to a canonical direction. `to_gltf_frame()` is a fixed change of axes and keeps each clip's heading as filmed.

**Tests.** `tests/test_convert.py` pins this:

- A synthetic standing pose with a 180° yaw (facing the camera in GVHMR's frame) comes out upright, facing +Z, with its left at +X and an identity pelvis rotation.
- `GVHMR_TO_GLTF` is a rotation that keeps up.
- On the 10-frame walk fixture, the converted body stands up and faces +Z. This test needs the SMPL-X model and skips without it.

## Canonical skeleton (stage 5.3, M1.8)

`anim8te/skeleton.py` defines the skeleton every library clip uses: the 22 SMPL-X body joints in SMPL-X order (so GVHMR's `body_pose[i]` drives bone `i + 1`), renamed with Godot's `SkeletonProfileHumanoid` names from the GDD §4 stage 5 table, with the SMPL-X parent table (`PARENTS`, root Hips). No fingers, jaw or eyes.

**Rest pose.** `canonical_skeleton(betas)` poses the SMPL-X neutral model at zero pose with the performer's shape. Every rest rotation is the identity and each bone's rest translation is the offset from its parent (`rest_offsets()`), so GVHMR's parent-relative rotations apply without re-expression. The SMPL-X model frame at rest is already glTF's (Y-up, facing +Z, left at +X). Its origin is not the floor: on the walk fixture's shape, Hips sits at y = -0.34 m and the joints span 1.53 m from toes to the head joint (the head joint is at the skull's base, not its top). Ground alignment (M1.9) puts the clip on y = 0.

**One shape per performer (G0).** `performer_betas(library, performer, clip_betas, source_clip)` returns `library/performers/<id>/betas.json` when it exists; otherwise it stores the clip's `betas` there and returns them. The first clip of a performer fixes the shape; later clips reuse it, whatever their own fit says (M0.7 measured a 6 cm stature spread across takes). QC compares each clip's `betas` against this reference (M3.5).

**Tests.** `tests/test_skeleton.py`: each SMPL-X joint maps to exactly one humanoid name and the 22 names are the profile's body bones; the parent table is one tree rooted at Hips with parents before children; the hierarchy is anatomical; the rest pose from the fixture's `betas` is upright, left at +X, toes forward (needs the SMPL-X model); the performer's shape is stored once and reused.

## Export (stage 5.7, M1.10)

`anim8te export <clip_id>` (`anim8te/stages/export.py`) turns `clean/motion.npz` into the clip's `motion.glb` with `pygltflib` and sets the status to `exported`.

**Layout.** A scene root node `Armature`, then one node per canonical bone in SMPL-X order, parented as in `PARENTS`. No mesh: the library GLB is skeleton only (66 KiB for the 155-frame walk). Rest rotations are the identity and rest translations are `rest_offsets()`, except Hips, which is lifted by the rest sole height (`sole_y`, stored in `motion.npz` since M1.10) so the rest pose stands on y = 0. That keeps Godot's retarget, which scales Hips motion by the rest Hips height, consistent with the grounded animation: the walk's rest Hips is 0.94 m up and its animated Hips 0.93 to 0.95 m. One skin over the 22 joints (inverse bind matrices are the negated rest world positions) makes importers build a skeleton from it.

**Straight spine (M2.12).** The rest translations of Spine, Chest, UpperChest, Neck and Head (`STRAIGHT_BONES`) point straight up (+Y) with their SMPL-X lengths kept; every other offset and every rotation is written unchanged. SMPL-X's rest spine is kinked: on perf01 the Hips>Spine offset leans 12 degrees back, Chest>UpperChest 27 degrees forward, UpperChest>Neck 10 degrees back and Neck>Head 8 degrees forward. Godot's humanoid retarget with "overwrite axis" transfers bone directions rather than rotations from rest, so the kink reached the mannequin as a hunch: on the walk, the mannequin's Chest>UpperChest segment leaned 33 to 40 degrees forward (median 37) and the head was pushed forward. With the straight rest it leans 5.5 to 12 degrees (median 10), UpperChest>Neck -10 to -3 and Neck>Head 3 to 8 (measured per frame on `scenes/mannequin_preview.tscn`, 154 frames). The cost is that the GLB's rest joints no longer sit exactly where SMPL-X puts them: on perf01 the Neck moves 3.6 cm, Chest 2.6, Spine 2.2, Head 1.9, and the arms, which hang off UpperChest, about 1 cm. Legs and feet, which carry contacts and ground alignment, do not move, and `clean/motion.npz` keeps the SMPL-X offsets for any measurement.

**Animation.** One animation named after the clip id, with a Hips translation channel and a rotation channel per bone, LINEAR, one key per frame at `frame / fps` (30 fps for GVHMR output). Sub-clip animations come with segmentation (M3).

**Checks on the walk clip.** The Khronos glTF-Validator (2.0.0-dev.3.10, `npm i gltf-validator`) reports no errors and no warnings, and one info, `UNUSED_OBJECT` on the skin, because no mesh uses it. Godot 4.7 imports it as a 22-bone `Skeleton3D` whose names and parents match `SkeletonProfileHumanoid`, plus an `AnimationPlayer` with `walk-ur7zdb` (5.13 s, 22 rotation tracks and a Hips position track, 1/30 s steps). The editor's bone-map auto-detection (`BoneMapper::auto_mapping_process`, run in the Advanced Import dialog) matches every name with its regexes: `hip`, `foot`, `(low|under).*leg`, `up.*leg`, `toe`, `hand`, `shoulder`, `(low|fore).*arm`, `up.*arm`, `neck` and `head`. Spine, Chest and UpperChest come from the chain under the shoulders' common parent.

**Tests.** `tests/test_export.py` builds a GLB from a synthetic motion and reads it back: node names and hierarchy, rest translations with the soles at 0 and the five spine and neck offsets vertical at their original lengths, inverse bind matrices, 23 channels, key times `i / fps`, values equal to the input. It also checks that `run_export` writes the file, is deterministic and sets the status, and that it refuses clips that are not cleaned and `motion.npz` files from before M1.10.

## End to end: one prompt to motion.glb (M1.11)

One fresh clip, `jog-qa61r5` (performer `perf01`, template `locomotion`), went through the four CLI stages on an M3 Max on 2026-10-07, with the worker already running on 127.0.0.1:8765:

```bash
uv run anim8te gen --performer perf01 --template locomotion --name jog \
  --prompt "The woman jogs at an easy, steady pace with relaxed arm swing"
uv run anim8te extract jog-qa61r5 --take 2
uv run anim8te clean jog-qa61r5
uv run anim8te export jog-qa61r5
```

| Stage | Wall-clock | Cost | What it did |
|---|---|---|---|
| `gen` | 19 s | $0.45 | 3 takes, H3 Max image-to-video, 5 s at 768P, 24 fps, 124 frames each, generated in parallel |
| take review | about 15 s | | contact sheet of the 3 takes; take 2 picked (1 and 3 drift back on the treadmill) |
| `extract` | 38 s | $0 (local) | upload, GVHMR on MPS (resample 24 → 30 fps, 155 frames; YOLO 5 s, ViTPose 9 s, recover and render 4 s), download of `hmr4d_results.pt` and `overlay.mp4` |
| `clean` | 2 s | | Savitzky-Golay (window 9, order 3), ground: soles lowered 2.7 cm |
| `export` | 1 s | | `motion.glb`, 66 KiB, 155 frames, 5.13 s |
| **Total** | **75 s** | **$0.45** | `meta.json` `created_at` 17:24:53 to `updated_at` 17:26:08 |

The 20-minute budget (GDD goal G1) holds with a wide margin. Stage 2 is the variable part: fal queue time was negligible here, and a busy queue or 1080P takes would add minutes, not seconds. A cold worker adds its start-up (a few seconds) and GVHMR's model load is already inside the 38 s. `uv run` builds the package on the first call after a change, about a second.

**In Godot.** `docs/scratch/glb_viewer/` is a throwaway Godot 4.7 project (the Gym is M2): it loads a `motion.glb` at runtime with `GLTFDocument`, draws each bone as a capsule, loops the animation and frames it from a front three-quarter view. Movie Maker recorded two loops in 3 s:

```bash
godot --path docs/scratch/glb_viewer --write-movie out.avi --fixed-fps 30 --quit-after 310 -- library/clips/<id>/motion.glb
```

The capture is `docs/captures/m1-jog-qa61r5-godot.mp4`. It shows 22 bones and the `jog-qa61r5` animation (5.13 s) jogging in place, facing +Z, with the soles on y = 0. The clip stays on the spot: root motion for treadmill locomotion is synthesized later (template `root_motion = "synthesize"`). The viewer calls `AnimationPlayer.advance(0)` after `play()`; without it the first recorded frame is the T-shaped rest pose.

## Per-frame features: features.json (M2.7)

Every `anim8te clean` run also writes `library/clips/<id>/features.json` (schema `ClipFeatures` in `anim8te/library.py`), computed from the cleaned, grounded motion in the glTF frame at the clip's fps: joint positions per frame (metres, `bone_names` order, from forward kinematics on the SMPL-X rest offsets in `clean/motion.npz`, not the straightened GLB rest), the Hips position and velocity as the root track, the magnitude of each joint's third derivative (jerk, m/s³, central differences), and per-frame contacts for LeftFoot, RightFoot, LeftToes and RightToes. The Gym overlays (GDD §6.4), QC and segmentation read this file instead of recomputing, so they agree. About 110 KB for a 155-frame clip.

**Contacts.** A joint is in contact when its sole height (its height minus its rest height above the soles, as in ground alignment) is under `height_m` and its horizontal speed relative to the ground is under `speed_mps`; runs shorter than `min_frames` are dropped. The parameters are the `contacts` filter in `meta.json` (`--no-contacts`, `--set contacts.speed_mps=0.6`); defaults `height_m` 0.04, `speed_mps` 0.8, `min_frames` 3, `ground_velocity` "auto". Detection only; foot locking is M3.1.

**Treadmill clips need a moving ground.** In GVHMR's world frame a treadmill clip stays on the spot, so a planted foot slides back at belt speed: on `walk-ur7zdb` the stance foot moves at about -0.6 to -1.0 m/s along Z while the swing foot comes forward at up to +2 m/s. A world-space speed threshold finds no contacts at all. `ground_velocity: "auto"` estimates the ground's (x, z) velocity as the median velocity of the lowest foot joint per frame: (0.01, -0.79) m/s on the walk, (0.01, -0.89) on `jog-qa61r5`, and about zero for a clip that is not on a treadmill. An explicit `[x, z]` overrides it.

**Tuning on the two clips.** With the default height gate, raising `speed_mps` never marks a swing foot (it is always over 4 cm up when it moves fast), so the speed threshold only sets how much of each stance is kept:

| `speed_mps` | walk-ur7zdb | jog-qa61r5 |
|---|---|---|
| 0.4 | alternating, but some stances split in two | short stances (3 frames), several missed |
| 0.6 | every stance, alternating | every stance, 4 frames each |
| 0.8 (default) | every stance, plus the first 7 frames standing | every stance, 5 to 6 frames |
| 1.0 | stances widen into double support | 6 to 7 frames |

The jog needs the looser threshold because GVHMR's planted foot does not move at a steady belt speed: its speed relative to the belt dips under 0.4 m/s for only about 3 frames of each 0.25 s stance. That is foot skate against the belt, which QC (M3.5) measures and foot lock (M3.1) fixes. The default is tuned on these two treadmill clips; revisit it with the first overground and traversal clips.

**Tests.** `tests/test_features.py` runs detection on a synthetic walk (1 s cycle, 60 % stance, noise on heights and velocities), on a treadmill and overground: contacts match stance in over 90 % of frames, never while the foot is up, and left and right heel strikes alternate. It also checks that a treadmill walk finds no contacts with a still ground, the ground-velocity estimate, short-run removal, the derivatives, the parameter validation, and the file written by `anim8te clean` (and emptied by `--no-contacts`).
