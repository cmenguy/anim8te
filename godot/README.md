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

## Scenes

- `main.tscn`: the entry scene. It instances the calibration level, holds `Character` (the default mannequin, in its rest pose) and the orbit camera.
- `mannequin_preview.tscn`: the mannequin playing the sample clip `walk-ur7zdb` in a loop through the editor import path (an `AnimationPlayer` whose `root_node` is the mannequin). Open it and press F6 to check an import setting change.
- `calibration_level.tscn`: the grey-box level (GDD §6.1), with a neutral procedural sky, one directional light and ACES tone mapping. `scripts/calibration_level.gd` builds the props in code (it is a `@tool` script, so they show up in the editor too). Every prop is a `StaticBody3D` with collision and a size label; the ground's grid shader (`assets/shaders/grid.gdshader`) draws 1 m and 10 cm lines in world space, with the X axis in red and the Z axis in blue.

Orbit camera (`scripts/orbit_camera.gd`): left or right drag orbits, middle drag or shift + drag pans, the wheel zooms, and F focuses on the character.

## Default mannequin

`assets/mannequin/` holds Quaternius' *Universal Base Characters* (Standard pack, CC0, `LICENSE.txt` next to it): the male full-body glTF with its eyes and eyebrows. Its textures are downscaled from 2048 to 1024 px, and two texture URIs in the `.gltf` that pointed at missing `*_png.png` files are corrected. The rig is Unreal-style (`root`, `pelvis`, `spine_01` ... `ball_r`, 65 bones with fingers).

Import settings (`Superhero_Male_FullBody.gltf.import`, node `Armature/Skeleton3D`):

- `retarget/bone_map`: `mannequin_bone_map.tres`, a `BoneMap` on `SkeletonProfileHumanoid`. 53 of the 56 profile bones are mapped (`pelvis` -> Hips, `spine_01/02/03` -> Spine/Chest/UpperChest, `clavicle_*` -> Shoulder, `thigh/calf/foot/ball_*` -> UpperLeg/LowerLeg/Foot/Toes, fingers 01/02/03 -> Proximal/Intermediate/Distal, thumb 01/02/03 -> Metacarpal/Proximal/Distal); only LeftEye, RightEye and Jaw are unmapped, and none of the three is required.
- Bones renamed to the profile names, skeleton made unique as `%GeneralSkeleton`.
- Rest fixer: retarget method "Overwrite Axis", fix silhouette on, apply node transforms, normalize position tracks, reset bone poses after import.

Library clips go through the same profile. `assets/sample_clips/walk-ur7zdb.glb` is a copy of the M1 walk (`library/clips/walk-ur7zdb/motion.glb`, 66 KiB) imported as an `AnimationLibrary` with `canonical_bone_map.tres` (the identity map on the 22 canonical bones), the same retarget settings and loop on. Its tracks come out as `%GeneralSkeleton:<Bone>`, so they drive any model imported this way; the Hips position track is normalized by the clip's rest hip height and rescaled by the mannequin's (`motion_scale` 0.95 m).

The sample clip is the editor-path reference only. The app loads `motion.glb` files from `library/` at runtime (M2.4); clips are not copied here otherwise.
