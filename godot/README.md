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

Library clips are not copied here: the app loads `motion.glb` files from `library/` at runtime.
