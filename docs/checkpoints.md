# Body models and GVHMR checkpoints

Downloaded for M0.3. None of these files go in git: SMPL, SMPL-X and GVHMR are non-commercial research licenses (GDD §10), and the files are large.

**Location:** `~/motion-ai-checkpoints/` on the Mac (6.2 GB). It mirrors GVHMR's `inputs/checkpoints/` tree, so on the GPU box (M0.6) the directory can be copied or symlinked to `GVHMR/inputs/checkpoints`.

```
~/motion-ai-checkpoints/
├── body_models/smplx/SMPLX_{NEUTRAL,MALE,FEMALE}.npz
├── body_models/smpl/SMPL_{NEUTRAL,MALE,FEMALE}.pkl
├── gvhmr/gvhmr_siga24_release.ckpt
├── hmr2/epoch=10-step=25000.ckpt
├── vitpose/vitpose-h-multi-coco.pth
└── yolo/yolov8x.pt
```

| File | Bytes | Size | Source |
|---|---:|---:|---|
| `body_models/smplx/SMPLX_NEUTRAL.npz` | 108,752,058 | 104 MB | SMPL-X v1.1 (NPZ+PKL) zip |
| `body_models/smplx/SMPLX_MALE.npz` | 108,753,445 | 104 MB | same |
| `body_models/smplx/SMPLX_FEMALE.npz` | 108,794,146 | 104 MB | same |
| `body_models/smpl/SMPL_NEUTRAL.pkl` | 247,186,228 | 246 MB | SMPL 1.1.0 for Python, renamed from `basicmodel_neutral_lbs_10_207_0_v1.1.0.pkl` |
| `body_models/smpl/SMPL_MALE.pkl` | 247,101,031 | 241 MB | same, from `basicmodel_m_...` |
| `body_models/smpl/SMPL_FEMALE.pkl` | 247,530,000 | 248 MB | same, from `basicmodel_f_...` |
| `gvhmr/gvhmr_siga24_release.ckpt` | 163,508,011 | 161 MB | GVHMR release |
| `hmr2/epoch=10-step=25000.ckpt` | 2,709,494,041 | 2.5 GB | GVHMR release |
| `vitpose/vitpose-h-multi-coco.pth` | 2,549,075,546 | 2.4 GB | GVHMR release |
| `yolo/yolov8x.pt` | 136,867,539 | 145 MB | GVHMR release |

## Where they come from

- **SMPL-X** (https://smpl-x.is.tue.mpg.de/, account and license required): under "SMPL-X Model", the "SMPL-X v1.1 (NPZ+PKL)" download, `models_smplx_v1_1.zip`. Only the `.npz` files are kept. Skip the "removed head bun" variants (retrained shape space) and SMPL-X 2020 (neutral only). The zip's `version.txt` says "Version 1.0"; that file is stale. The model itself has 300 shape and 100 expression components (`shapedirs` is `10475 x 3 x 400`), which is v1.1.
- **SMPL** (https://smpl.is.tue.mpg.de/, account and license required): "version 1.1.0 for Python 2.7 (female/male/neutral, 300 shape PCs)", `SMPL_python_v.1.1.0.zip`. It is the only release with a neutral model. The files are renamed to the `SMPL_{GENDER}.pkl` names GVHMR expects; `LICENSE.txt` from the zip sits next to them. The pickles reference `chumpy`, so the worker environment needs it installed (GVHMR's requirements cover this).
- **GVHMR, HMR2, ViTPose, YOLO**: the official source is the Google Drive folder in GVHMR's `docs/INSTALL.md`. On 2026-10-06 that folder returned "Too many users have viewed or downloaded this file recently", so the files came from the Hugging Face mirror `camenduru/GVHMR` (same tree). Every file's SHA256 matched the mirror's LFS hash. `dpvo/dpvo.pth` is skipped: the pipeline runs GVHMR with `-s` (static camera), which does not use DPVO.

SHA256, to check a copy on the GPU box:

```
4fae7da2de388d5da3514cb27a2d003f364dacb280e9cf88972b710e589c6b91  gvhmr/gvhmr_siga24_release.ckpt
2dcf79638109781d1ae5f5c44fee5f55bc83291c210653feead9b7f04fa6f20e  hmr2/epoch=10-step=25000.ckpt
50e33f4077ef2a6bcfd7110c58742b24c5859b7798fb0eedd6d2215e0a8980bc  vitpose/vitpose-h-multi-coco.pth
c4d5a3f000d771762f03fc8b57ebd0aae324aeaefdd6e68492a9c4470f2d1e8b  yolo/yolov8x.pt
```

To fetch the four again without Drive:

```bash
cd ~/motion-ai-checkpoints
for f in gvhmr/gvhmr_siga24_release.ckpt "hmr2/epoch=10-step=25000.ckpt" \
         vitpose/vitpose-h-multi-coco.pth yolo/yolov8x.pt; do
  curl -fL -C - -o "$f" "https://huggingface.co/camenduru/GVHMR/resolve/main/$f"
done
```

## Who uses what

- The GPU worker (M0.6) needs the whole tree.
- The Mac needs only `body_models/smplx/` for the `smplx` package in stage 5 cleanup (M1.6).
