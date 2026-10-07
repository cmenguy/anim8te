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

- `main.tscn`: the entry scene. It instances the calibration level, holds `Character` (a `ClipPlayer` driving the default mannequin, in its rest pose until a clip is picked), the orbit camera, `UI/LibraryPanel` (see "Library panel"), `UI/ClipViewer` (see "Clip Viewer") and `UI/CompareView` (see "Compare", hidden until toggled).
- `mannequin_preview.tscn`: the mannequin playing the sample clip `walk-ur7zdb` in a loop through the editor import path (an `AnimationPlayer` whose `root_node` is the mannequin). Open it and press F6 to check an import setting change.
- `runtime_retarget.tscn`: the mannequin playing a library clip loaded at runtime (`ClipPlayer`, see "Runtime retargeting"). `clip_id` defaults to `walk-ur7zdb`; `godot --path godot scenes/runtime_retarget.tscn -- --clip=jog-qa61r5` picks another.
- `calibration_level.tscn`: the grey-box level (GDD §6.1), with a neutral procedural sky, one directional light and ACES tone mapping. `scripts/calibration_level.gd` builds the props in code (it is a `@tool` script, so they show up in the editor too). Every prop is a `StaticBody3D` with collision and a size label; the ground's grid shader (`assets/shaders/grid.gdshader`) draws 1 m and 10 cm lines in world space, with the X axis in red and the Z axis in blue.

Orbit camera (`scripts/orbit_camera.gd`): left or right drag orbits, middle drag or shift + drag pans, the wheel zooms, F focuses on the character and C toggles follow: the orbit centre tracks the character on the ground plane (its hips, through `ClipPlayer.focus_position()`), keeping its height so the view does not bob. A click or wheel over a GUI control is left to the control (Godot passes wheel events on even past a control that stops the mouse, so the main camera would otherwise zoom along with Compare's 3D pane).

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

## Clip Viewer

`scripts/clip_viewer.gd` (`ClipViewer`, the bar along the bottom of `main.tscn`) is the Clip Viewer mode (GDD §6.3). Selecting a playable clip in the library panel plays it on the mannequin from frame 0; a partial clip is named in the bar and not played. The bar has frame step back and forward, play/pause, a timeline (one step per frame) to scrub, speed from 0.1x to 2x with a 1x reset, Loop, Follow (the camera, as C does) and Compare (next section), and shows the clip id, its frame count and rate, the current frame and the time. Keys: Space plays or pauses, Left/Right (or `,`/`.`) step a frame and pause, L toggles loop, V toggles Compare.

The transport lives in `ClipPlayer` (`set_playing`, `seek`, `seek_frame`, `step`, `speed`, `loop`, `current_clip`), so other modes can reuse it. A clip has one key per frame; `RuntimeClip.frame_count` and `fps` come from the keys (30 fps for GVHMR). Stepping wraps around when looping and stops at the ends otherwise; a non-looping clip stops on its last frame and Play starts it over. A looping animation wraps a seek to its length back to 0, so the last frame of a looping clip is shown 0.1 ms before it. Clips load in about 10 ms the first time and 0.2 ms from the cache, so switching needs no preloading. Check with:

```bash
godot --headless --path godot --script tests/check_clip_viewer.gd
```

It loads the main scene against the local library (needs two clips with a `motion.glb`), drives the bar and the player, and exits 1 on a failed check. Capture: `docs/captures/m2.6-clip-viewer.jpg`.

## Debug overlays

`scripts/clip_overlays.gd` (`ClipOverlays`, node `Character/Overlays` in `main.tscn`, a child of the `ClipPlayer` so it shares the clip's space) holds the Gym's debug overlays (GDD §6.4). Each overlay is its own node, a `DebugOverlay` (`scripts/overlays/`) drawing an unshaded `ImmediateMesh` over the character; all of them read the clip's `features.json` (`scripts/clip_features.gd`, `ClipFeatures`, parsed once per clip and cached, about 4 ms) and redraw for the player's current frame. The overlay panel (`scripts/overlay_panel.gd`, top right) has a check box per overlay; keys 1 to 6 toggle them in the same order.

| Key | Overlay | Draws |
|---|---|---|
| 1 | Foot contacts | a disk under each foot joint while `contacts` has it planted: green, or red when it slides (horizontal speed relative to the ground, the belt on a treadmill, over `slide_mps` 0.3 m/s, 1 cm per frame) |
| 2 | Root trajectory | the Hips track on the ground, the past second blue and the next second orange, and the facing arrow; treadmill clips stay on the spot until root motion (M3.2) |
| 3 | Velocity vectors | `root_velocity` from the Hips (cyan) and the hands' and feet's velocities (yellow), 0.2 m per m/s |
| 4 | Ground penetration | a red marker, disk and depth in mm on every joint more than 5 mm under the ground; foot joints by their sole, using `rest_heights_above_sole` (added to `features.json` in M2.8; re-run `anim8te clean` on older clips) |
| 5 | Skeleton wireframe | the extracted canonical skeleton (`joint_positions`) |
| 6 | Joint jerk heatmap | a marker per joint coloured by `joint_jerk` on a fixed scale, blue at 0 to red at 300 m/s³, so clips compare |

The overlays show the extracted motion, not the mannequin: `features.json` positions match the source skeleton to 0.1 mm, and the mannequin's own proportions put its feet a few centimetres wider and its hands higher, which the wireframe makes visible. Which overlays are on is kept across clip changes and saved in `user://gym_settings.cfg` (section `overlays`), so the next session starts with the same set. A clip without a usable `features.json`, or an overlay with nothing to draw (contacts filter off), is named in the panel. Check with:

```bash
godot --headless --path godot --script tests/check_overlays.gd
```

It plays two library clips with a `features.json` (needs the local library), steps every frame with all overlays on and checks each against the file, then checks the toggles across a clip change, keys 1 to 6, and a second session on the same settings file (its own, not the user's). On the M1 clips: the walk's contacts are 35 % sliding, the jog's 56 % (the skate noted in M2.7), and the jog's right toes go 8 mm under the ground on frames 86 and 87. Capture: `docs/captures/m2.8-debug-overlays.jpg` (jog: contacts, trajectory, velocity; jog: wireframe, jerk, penetration; walk: contacts, wireframe, trajectory).

## Video

Godot 4.7 decodes only Ogg Theora (`VideoStreamTheora`), so the app plays the `.ogv` copies the pipeline writes next to the mp4 files (decision Q6): `selected.ogv` (the take, 768x960 at 24 fps for H3 Max 768P) and `gvhmr/overlay.ogv` (GVHMR's render, in-camera overlay and global view side by side, 768x480 at 30 fps). Both are video only and keep the source's size, rate and frame count. `anim8te extract` writes them; `anim8te transcode <id>` does it for clips extracted before M2.9. Load one with `VideoStreamTheora.new()`, `file = <absolute path>`, in a `VideoStreamPlayer`. Check with:

```bash
godot --headless --path godot --script tests/check_video_playback.gd [-- --clip=<id>]
```

It plays both files of a library clip, checks length, playback rate, frame size, a seek to 3 s and the stop at the end, and exits 1 on a failed check.

## Compare

`scripts/compare_view.gd` (`CompareView`, `UI/CompareView` in `main.tscn`) is the Compare mode (GDD §6.3): the Compare toggle in the Clip Viewer bar (or V) covers the 3D view with three panes, the source take (`selected.ogv`) on the left, the 3D clip top right and GVHMR's overlay render (`gvhmr/overlay.ogv`) below it. The 3D pane is a `SubViewport` on the main world with its own orbit camera following the character, so the debug overlays show there too (their panel sits over it). A clip without its `.ogv` files says so in the pane title (`anim8te transcode <id>`).

The Clip Viewer bar drives all three: the `ClipPlayer`'s time is the clock and the videos follow it every frame, so play/pause, scrub, step, speed and loop apply to all three. Clip time t is video time t (GVHMR resamples the take to 30 fps without trimming). How the sync works, from Godot 4.7's `VideoStreamPlayer` and Theora sources:

- A `VideoStreamPlayer` advances by the process delta times `speed_scale`, like the `AnimationPlayer`, so at the same speed they stay together without seeking. Theora seeks cost 10 to 35 ms, so a playing video seeks only on a jump (loop, scrub, step) or past half a frame of drift; a paused one seeks whenever the clip's time moves, and that is frame-exact.
- `CompareView` processes after the `ClipPlayer` and before its own video children: it compares the clip's time with where the videos' update this frame will put them, and a seek there lands exactly (a seek makes the video skip its next update).
- A seek to exactly k / fps shows frame k - 1, so seeks land 0.1 ms later.
- On its last frame a running Theora video finds no next frame, stops and rewinds to 0; videos are held there with `paused`. `play()` and unpausing re-enable processing too late for that frame, so the video is seeked once more on the next. The frame time comes from the file's Theora header (`CompareView.theora_fps`; 24 fps for the take, 30 for the overlay).

Check with:

```bash
godot --headless --path godot --script tests/check_compare.gd [-- --clip=<id>]
godot --path godot --script tests/check_compare.gd             # also checks the frames on screen
```

It plays a library clip with both `.ogv` files in Compare mode and checks the drift between each video and the clip on every frame of a full 5 s play at 1x, at 0.5x and 2x, across a loop and to the end of a non-looping clip, plus scrubs, steps and pause. With a renderer (no `--headless`) it also zooms the 3D pane with the wheel and matches each video's texture, every frame, against the file's frames decoded by ffmpeg (`ANIM8TE_FFMPEG`, else `ffmpeg` on PATH). On the M1 jog: drift 0.1 ms at every speed, no corrective seeks while playing, 99.4 to 100 % of video frames on screen the expected one and the rest one frame off (frame-boundary ties), paused scrubs exact. The frame after a stall over 50 ms can show a stale picture (Theora outputs one frame per update); those samples are reported, not judged. Capture: `docs/captures/m2.10-compare.jpg`.

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
