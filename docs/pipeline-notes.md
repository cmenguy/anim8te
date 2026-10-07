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

**What the conversion does not do.** GVHMR's floor is not at y = 0. The walk clip's lowest foot joint sits 11 to 14 cm up and the vault's 12 cm or more. The SMPL-X `*_foot` joint is at the ball of the foot, a few cm above the sole. Ground alignment is a cleanup filter (GDD §4 stage 5.4), as is turning a clip's heading to a canonical direction. `to_gltf_frame()` is a fixed change of axes and keeps each clip's heading as filmed.

**Tests.** `tests/test_convert.py` pins this:

- A synthetic standing pose with a 180° yaw (facing the camera in GVHMR's frame) comes out upright, facing +Z, with its left at +X and an identity pelvis rotation.
- `GVHMR_TO_GLTF` is a rotation that keeps up.
- On the 10-frame walk fixture, the converted body stands up and faces +Z. This test needs the SMPL-X model and skips without it.
