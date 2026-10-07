# glb_viewer

Throwaway Godot 4.7 project that plays a library `motion.glb` as capsule bones, used for the M1.11 capture. The Gym (M2) replaces it.

```bash
godot --path docs/scratch/glb_viewer -- library/clips/<id>/motion.glb                     # window
godot --path docs/scratch/glb_viewer --write-movie out.avi --fixed-fps 30 --quit-after 310 -- library/clips/<id>/motion.glb
```
