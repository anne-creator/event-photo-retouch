---
name: event-photo-retouch
description: Repair lighting in event photos, then apply natural multi-person skin finishing. Preserve original people, text, composition and dimensions, and deliver before/after comparisons.
metadata:
  short-description: Lighting repair and natural group-photo finishing
---

Default to lighting repair first, then natural multi-person skin finishing at strength 0.3. A user's request for lighting only or a different finish overrides this default. Reuse this installed workflow without asking users to repeat these defaults.

Inspect a named contact sheet and a representative original from each lighting situation. Assess faces and surroundings separately: glare/halos, projected stripes, clipped channels, shadow exposure and mixed color casts. Different photos need different corrections, rather than one shared exposure preset. Keep originals untouched and start from originals, not previous exports.

Use the host's image editing model to create an illumination reference, following that tool's image-inspection requirements. Use the exact original as the edit target, with the [reference prompt](references/workflow.md#illumination-reference). Save the reference and prompt. If a validated reference already exists, reuse it. Do not silently switch to an external paid API. The scripts do not call an image-generation service themselves. If no image tool is available, use a user-supplied reference or explain that dependency.

A generated edit may replace faces or text even when instructed otherwise. Never deliver it directly. Run `run.sh light` to transfer only smooth light/color gains onto the original pixels. Preserve image coordinates and texture; do not enlarge a generated image and call it original-resolution restoration. The input contract is oriented 8-bit SDR. Supported HEIC is checked before conversion; high-bit/HDR inputs require an explicit SDR development.

For strong glare, distinguish luminous lamp/screen cores from unwanted spill on walls, clothes and skin. Mark genuine emitters with `emitter_regions`; do not protect every white pixel as a light source. Use the stronger v2 lighting settings, then adjust scene regions after inspection. The medium-scale reference layer is disabled over detected faces. If face detection is unavailable it is disabled everywhere unless manually reviewed identity regions are provided.

Projected letters or narrow bands need localized treatment. Read the [artifact and identity rules](references/workflow.md#projected-stripes-and-identity) when they occur. A source-derived artifact mask can estimate an illumination gain, but cannot recover clipped skin or hidden facial features. Never solve residual stripes by pasting a generated face, increasing the medium layer on eyes, or inventing eye/teeth/hair detail. Report unresolved regions honestly. A single targeted reference retry is reasonable; inspect persistent failures instead of repeatedly generating replacements.

After lighting passes visual review, run `run.sh beauty` on its lossless PNG output. Local CPU models use high-confidence skin masks, with eyes/glasses, nose, lips and teeth excluded. Disable whitening, generated inpainting and reshaping. Skip faces smaller than 100 source pixels or below confidence 0.8, and report the skip. Verify that PNG pixels outside the skin mask and inside protected features are unchanged relative to the lighting render. These guarantees do not apply to a recompressed JPEG.

Inspect every final full frame and key face, text and strong-light crops. Check believable light, skin tone, readable original text, residual bands, halos and mask seams. Automated hashes, dimensions and clipping counts support this check; they do not replace it. Save original-size sRGB PNG/JPEG, same-scale before/after comparisons, and separate references/receipts. Treat generated references, rejected candidates and final exports as distinct artifacts.

For commands, manifests, tuning and validation, read [workflow.md](references/workflow.md) only as needed. Resolve all scripts relative to this skill's installed folder. `run.sh doctor` verifies model hashes; installation supplies the runtime. Do not reinstall working dependencies for each batch.

Reduce token overhead by reusing scripts, accepted references and hash-verified renders; batch independent local operations and return compact summaries while retaining full receipts on disk. A beauty-only adjustment reuses the lighting result. Keep the image model, actual input resolution, per-photo lighting judgment and visual inspection unchanged. Distinguish conversation tokens, image calls and local inference. Unknown image usage is unknown, not zero; token totals cannot reliably predict an account's weekly-limit percentage.
