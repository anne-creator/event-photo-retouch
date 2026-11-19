# Setup and validation

Detailed setup, processing checks and release notes for v0.2.0.

## Install

Run this single command in Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/anne-creator/event-photo-retouch/v0.2.0/install.sh | bash
```

The installer supports macOS, Linux and WSL. It installs a private Python environment, pinned dependencies and approximately 265 MB of checksum-verified model weights. If a suitable Python is missing, it provisions Python 3.11 through [uv](https://docs.astral.sh/uv/). It does not modify your shell profile. Network access and curl are required. Native Windows is not covered.

The skill goes into `${CODEX_HOME:-$HOME/.codex}/skills/event-photo-retouch`. An existing installation is moved into the adjacent `skill-backups` directory. Models are cached under `${XDG_CACHE_HOME:-$HOME/.cache}/event-photo-retouch/models`. Set `EVENT_PHOTO_MODELS` to use another cache or `PYTHON` to select an existing Python 3.11 through 3.14 interpreter.

You can [inspect the installer](../install.sh) before running it. To install a local checkout:

```bash
bash install.sh --source "$PWD"
```

For an offline model cache, add `--models-from /path/to/verified/models`. Python packages must already be available or installable.

## Use it in Codex

Attach original photos or provide their folder, then say:

> Use $event-photo-retouch on these photos.

The default is **lighting repair first, natural multi-person finishing second**, with original dimensions and before/after comparisons. Specify exceptions such as “lighting only” or “one sample first” when needed. Reopen the chat if a new installation is not discovered immediately.

The host needs an image-editing tool to make a new illumination reference. Its image calls may count toward the host's allowance. This package does not include image-generation credits or silently call a paid API. With an existing reference, the rendering and skin finishing run locally. The skill also works with a user-supplied reference when no image tool is available.

Check the installation:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/event-photo-retouch/run.sh" doctor
```

For CLI commands, manifests, scene controls and artifact masks, see [the workflow guide](workflow.md).

## What changed in v0.2.0

- Stronger light transfer with regional exposure and contrast control.
- Separate protection for real lamp/screen cores, so unwanted bright spill is not automatically protected.
- An additional medium-scale lighting layer, excluded from detected face regions.
- Opt-in, source-derived illumination repair for localized projected stripes.
- Clipped-face diagnostics and explicit review of unresolved stripes.
- A portable installer and independently implemented CPU inference backend, with no unlicensed adapter code bundled.

This comes from two observed failures: broad corrections left projected bands intact, and whole-image generative edits changed faces. The final renderer keeps source geometry and texture. It does not deliver a generated face as a repair.

## Limits and validation

Fully clipped highlights and facial details hidden by projected light cannot be recovered faithfully from a single JPEG. Artifact repair can reduce illumination differences, but may leave residual stripes. Mask edges, shading and faces need visual inspection. No successful full removal of the difficult projected-face example is claimed here.

The pipeline currently processes 8-bit SDR. It applies EXIF orientation, converts ICC-tagged input to sRGB and rejects unsupported high-bit/HDR input for explicit development. Small or low-confidence faces are skipped. Original coordinates stay fixed, but changing light can still affect perceived facial contrast.

The exact skin-mask and protected-feature checks apply to the lossless PNG compared with the lighting PNG. JPEG recompression has different pixel values. Every final photo still needs full-frame and face/text/light-region review.

Validated on macOS with Python 3.11: clean installation in a path containing spaces, real CPU inference on two photos and seven eligible faces, and eight automated checks covering pixel preservation, localized stripe correction, emitter handling, clipping, dimensions, input rejection and cache integrity. The public test suite requires no model download:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Token savings come from cached references, hash-verified resumption, local batch execution and concise logs. Input resolution, image-model quality and visual review remain unchanged. Local inference itself uses no LLM tokens; agent operation and image calls are separate. A weekly-limit percentage cannot be predicted reliably from token totals.

## License and model attribution

Code and skill instructions: [MIT](../LICENSE). Downloaded skin models: Apache-2.0. Downloaded face detector: MIT. Original models, revisions, modifications and notices are documented in [NOTICE](../NOTICE) and [models.json](../models.json). Photographs and depicted likenesses, logos and event materials are not licensed for reuse by this repository.

## 中文使用说明

在终端运行上面的安装命令，然后在 Codex 上传原图或给出文件夹，说“用 $event-photo-retouch 修这些照片”即可。默认先按各张照片的光线修光，再做多人自然美颜，保留人物、文字、构图和原尺寸，并输出前后对比。需要先做小样或只修光时，直接说明。

新版加强了光晕、杂散白光和局部投影光条的处理。已过曝丢失的脸部细节无法真实恢复，流程不会通过换脸补造。安装免费，本地推理不消耗 LLM token；图像参考生成和 Codex 的操作、验收仍使用相应账号额度。
