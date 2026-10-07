# godot

Godot project for the Gym and the Workflow Manager (GDD §6, §7). Pinned to Godot 4.7 (`config/features` in `project.godot`), Forward+ renderer; one unit is one metre, Y-up, right-handed.

## Open and run

Install Godot 4.7 (`brew install --cask godot`, which puts `godot` on the PATH), then from the repo root:

```bash
godot --editor --path godot      # open in the editor (F5 runs the main scene)
godot --path godot               # run the main scene without the editor
godot --headless --path godot --import   # first-time import, e.g. in CI
```

The editor cache `.godot/` is git-ignored and rebuilt on first open.

## Layout

| Path | Holds |
|---|---|
| `scenes/` | `.tscn` scenes; `main.tscn` is the main scene |
| `scripts/` | GDScript (`.gd`, plus the `.gd.uid` files Godot writes; commit both) |
| `assets/` | meshes, textures, the mannequin, each with its license file next to it |
| `ui/` | Control scenes and themes for the Workflow Manager |
| `addons/` | editor plugins and GDExtensions |
| `tests/` | headless check scripts (`godot --headless --path godot --script tests/<name>.gd`) |

## Scenes

- `main.tscn`: the entry scene. It instances the calibration level, holds `Character` (the default mannequin, in its rest pose), the orbit camera and `UI/LibraryPanel` (see "Library panel").
- `mannequin_preview.tscn`: the mannequin playing the sample clip `walk-ur7zdb` in a loop through the editor import path (an `AnimationPlayer` whose `root_node` is the mannequin). Open it and press F6 to check an import setting change.
- `runtime_retarget.tscn`: the mannequin playing a library clip loaded at runtime (`ClipPlayer`, see "Runtime retargeting"). `clip_id` defaults to `walk-ur7zdb`; `godot --path godot scenes/runtime_retarget.tscn -- --clip=jog-qa61r5` picks another.
- `calibration_level.tscn`: the grey-box level (GDD §6.1), with a neutral procedural sky, one directional light and ACES tone mapping. `scripts/calibration_level.gd` builds the props in code (it is a `@tool` script, so they show up in the editor too). Every prop is a `StaticBody3D` with collision and a size label; the ground's grid shader (`assets/shaders/grid.gdshader`) draws 1 m and 10 cm lines in world space, with the X axis in red and the Z axis in blue.

Orbit camera (`scripts/orbit_camera.gd`): left or right drag orbits, middle drag or shift + drag pans, the wheel zooms, and F focuses on the character.

## Default mannequin

`assets/mannequin/` holds Quaternius' *Universal Base Characters* (Standard pack, CC0, `LICENSE.txt` next to it): the male full-body glTF with its eyes and eyebrows. Its textures are downscaled from 2048 to 1024 px, and two texture URIs in the `.gltf` that pointed at missing `*_png.png` files are corrected. The rig is Unreal-style (`root`, `pelvis`, `spine_01` ... `ball_r`, 65 bones with fingers).

Import settings (`Superhero_Male_FullBody.gltf.import`, node `Armature/Skeleton3D`):

- `retarget/bone_map`: `mannequin_bone_map.tres`, a `BoneMap` on `SkeletonProfileHumanoid`. 53 of the 56 profile bones are mapped (`pelvis` -> Hips, `spine_01/02/03` -> Spine/Chest/UpperChest, `clavicle_*` -> Shoulder, `thigh/calf/foot/ball_*` -> UpperLeg/LowerLeg/Foot/Toes, fingers 01/02/03 -> Proximal/Intermediate/Distal, thumb 01/02/03 -> Metacarpal/Proximal/Distal); only LeftEye, RightEye and Jaw are unmapped, and none of the three is required.
- Bones renamed to the profile names, skeleton made unique as `%GeneralSkeleton`.
- Rest fixer: retarget method "Overwrite Axis", fix silhouette on, apply node transforms, normalize position tracks, reset bone poses after import.

Library clips go through the same profile. `assets/sample_clips/walk-ur7zdb.glb` is a copy of the M1 walk (`library/clips/walk-ur7zdb/motion.glb`, 66 KiB) imported as an `AnimationLibrary` with `canonical_bone_map.tres` (the identity map on the 22 canonical bones), the same retarget settings and loop on. Its tracks come out as `%GeneralSkeleton:<Bone>`, so they drive any model imported this way; the Hips position track is normalized by the clip's rest hip height and rescaled by the mannequin's (`motion_scale` 0.95 m).

The sample clip is the editor-path reference only. The app loads `motion.glb` files from `library/` at runtime (next section); clips are not copied here otherwise.

## Library panel

`scripts/library_panel.gd` (`LibraryPanel`, docked left in `main.tscn`) lists the clips under `<library>/clips/*/` with name, tags, status and QC badge, scanned by `scripts/library_scanner.gd` (`LibraryScanner`) on start and on Refresh. It reads `meta.json` (name, tags, status) and `qc.json` (status: `ok`, `!` warn, `x` fail, `...` pending, `-` none) and checks for `motion.glb`. A clip with a file missing or unreadable stays in the list, greyed, with status `partial`; its tooltip says what is wrong. Selecting a row emits `clip_selected(id, playable)` (playable means `motion.glb` exists); the Clip Viewer (M2.6) plays it.

The library root, for the panel and `ClipPlayer` alike (`LibraryScanner.resolve_root`): the node's `library_path` export, else a `--library=<path>` user argument (`godot --path godot -- --library=/path/to/library`), else `ANIM8TE_LIBRARY`, else `<repo>/library`. The path field at the top of the panel switches library on Enter. Check with:

```bash
godot --headless --path godot --script tests/check_library_scanner.gd
```

It builds a throwaway library under `user://` (complete, partial and broken clips), checks the scan and the panel, prints the real library's list and exits 1 on a mismatch. Capture: `docs/captures/m2.5-library-panel.jpg`.

## Runtime retargeting

`scripts/clip_player.gd` (`ClipPlayer`) plays library clips on a model with no import step: `scripts/runtime_clip.gd` (`RuntimeClip`) reads `library/clips/<id>/motion.glb` with `GLTFDocument`, and a `RetargetModifier3D` on `SkeletonProfileHumanoid` drives the model. The library root is resolved as in the library panel (next section). Node layout, built in `_ready`:

```
ClipPlayer (Node3D)
  Armature (Node3D)
    Skeleton3D               canonical source: the 22 bones, no mesh
      RetargetModifier3D     profile = SkeletonProfileHumanoid, use_global_pose = false, enable = all
        GeneralSkeleton      the model's Skeleton3D, moved here with its meshes
  AnimationPlayer            root_node = ClipPlayer; one animation per loaded clip
```

The source skeleton is persistent: loading a clip adds its animation to the player's library, and playing it sets that clip's rests (bone offsets differ per performer) and `motion_scale`. Clips are converted once for the driven model and cached; `set_model()` swaps the model and reloads.

Gotchas, all measured on `walk-ur7zdb` and `jog-qa61r5`:

- **The target must be a direct child of the modifier.** `RetargetModifier3D` only drives `Skeleton3D` nodes that are its direct children; with the whole model scene under it nothing moves. `set_model()` takes the model's `Skeleton3D` out (clearing owners, keeping its transform) and frees the rest. The meshes follow because they are children of the skeleton (`skeleton = ".."`).
- **Rests: no importer, so no rest fixer.** `motion.glb` has identity rest rotations on SMPL-X's A-pose. The modifier transfers rotations relative to rest, so used as is the A/T-pose difference lands on the model as a constant offset (18 degrees at the upper arms). `RuntimeClip` re-expresses the clip on the driven model's own rest frames: each bone gets a constant frame change B (the model's rest frame, swung onto the clip's bone direction), keys become `B_parent^-1 * key * B` and rest offsets `B_parent^-1 * offset`. The clip's posed skeleton is unchanged (0 m difference on every joint) and only the rest moves. Using the model's rest rather than the profile's reference pose also absorbs the bends the mannequin keeps after "fix silhouette" (3 degrees at the elbows, 6 at the knees).
- **No bone renaming is needed.** `motion.glb` bones already carry the profile names (`anim8te export`); a clip with a bone outside the reference is rejected.
- **`motion_scale` scales position tracks.** The animation mixer multiplies bone position tracks by the skeleton's `motion_scale`, so the Hips track is stored divided by the clip's rest hip height and `motion_scale` is set to that height (what the importer's "normalize position tracks" does). Without it the clip sinks about 6 cm.
- **Local, not global pose.** In local mode the model keeps its own bone lengths and the hips move by `target_rest + (source - source_rest) x target.motion_scale / source.motion_scale`, a delta from rest. Global mode copies model-space positions onto every bone, which stretches the model to the clip's proportions (thighs at 0.89 of their length on the mannequin), and it ignores `enable`.
- **Modifiers apply during the skeleton update.** After `seek()`, read bone poses on the next frame.

Against the clip itself, the mannequin's bone directions match to 0.00 degrees and its hip height change to 0.00 cm on both clips. The editor import path (M2.3) is 3 to 14 degrees off on the spine, elbows and legs, from its own rest fixing, and places the hips by absolute scaling rather than from rest (the two differ by a constant 5 cm in z on the mannequin, its rest hip offset). Check it with:

```bash
godot --headless --path godot --script tests/check_runtime_retarget.gd [-- --clip=<id>]
```

It needs the local library and exits 1 if a bone direction drifts past 1 degree or the hip height past 0.5 cm. Capture: `docs/captures/m2.4-runtime-retarget.jpg`.
