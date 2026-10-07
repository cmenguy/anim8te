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

- `main.tscn`: the entry scene. It instances the calibration level, holds `Character` (a capsule placeholder until the M2.3 mannequin) and the orbit camera.
- `calibration_level.tscn`: the grey-box level (GDD §6.1), with a neutral procedural sky, one directional light and ACES tone mapping. `scripts/calibration_level.gd` builds the props in code (it is a `@tool` script, so they show up in the editor too). Every prop is a `StaticBody3D` with collision and a size label; the ground's grid shader (`assets/shaders/grid.gdshader`) draws 1 m and 10 cm lines in world space, with the X axis in red and the Z axis in blue.

Orbit camera (`scripts/orbit_camera.gd`): left or right drag orbits, middle drag or shift + drag pans, the wheel zooms, and F focuses on the character.

Library clips are not copied here: the app loads `motion.glb` files from `library/` at runtime.
