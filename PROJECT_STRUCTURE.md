# Project Structure

Updated 2026-11-19. Public release: v0.2.0.

## Project Structure

- `SKILL.md`: agent entry point and default lighting/beauty behavior.
- `scripts/lighting_field.py`: original-pixel light/color transfer and localized artifact-light repair.
- `scripts/onnx_backend.py`: independent CPU face, skin and blend-layer inference.
- `scripts/beauty_finish.py`: protected skin-only finishing and preservation receipts.
- `scripts/download_models.py`, `models.json`: checksum-pinned release asset installation.
- `install.sh`, `run.sh`, `requirements.txt`: portable runtime installation and command entry point.
- `references/workflow.md`: commands, scene configuration, failure handling and resource use.
- `examples/`: selected full-width original/AI-edit display pair, provenance in `selected-pair.json`, and earlier source-pixel previews/checks in `manifest.json`.
- `tests/test_pipeline.py`: synthetic preservation and error-handling tests.
- `LICENSE`, `NOTICE`, `third_party/`: code license and model attribution.

## Workflow

Install once, inspect original light, generate or reuse an illumination reference, run `run.sh light`, visually review, run `run.sh beauty`, then inspect and export comparisons. Receipts and masks belong in the user's output folder. Originals and model-reference texture are not overwritten or substituted.

## Module Inputs And Outputs

- Lighting: original/reference/scene JSON to original-size sRGB PNG/JPEG, gain field and receipt.
- Beauty: lighting PNG manifest and strength to finished PNG/JPEG, skin mask and receipt.
- Models: pinned manifest to shared local model cache; SHA-256 required before reuse.
- Installer: release archive or checkout to private skill runtime; prior installation is backed up outside skill discovery.

## Data Stats Change

The README displays one user-selected pair vertically, original above and edited below, at full content width. Native images are 3840 x 2160 and 1672 x 941 pixels. The selected after image is a direct AI edit. Two earlier source-pixel demonstration pairs and their seven-face checks remain versioned separately. Three model assets total 265,230,905 bytes. Model weights, personal paths, project memories and private validation images are excluded from Git.

## Feature Specs

- Default sequence: scene-dependent light repair, then natural multi-face finishing at 0.3.
- Stronger v2 light transfer, emitter-specific white protection, face-excluded medium layer and opt-in source-only artifact illumination repair.
- No geometric warps or generated source texture; clipped facial detail is an explicit limitation.
- Beauty excludes key features and verifies unchanged PNG pixels outside the skin mask.
- Hash-verified resumption, no source overwrites, no automatic paid image API.
- macOS/Linux/WSL installer, isolated dependencies, automatic Python provisioning if needed.

## Maintenance Log

- 2026-11-19: Packaged the established photo workflow for public installation; improved lighting controls using glare and projected-stripe failure cases. Eight automated checks and clean-install/real-photo inference checks passed on macOS Python 3.11.

- 2026-11-19: Replaced the README comparison layout with the exact user-selected original and AI-edit pair, displayed separately at full content width. Retained native pixels, documented provenance and preserved earlier processing checks.
