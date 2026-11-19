# Running the workflow

Resolve the installed skill directory, usually `${CODEX_HOME:-$HOME/.codex}/skills/event-photo-retouch`. Run its `run.sh`. The installer supports macOS, Linux and WSL with curl. It reuses Python 3.11 through 3.14, or provisions a private Python 3.11 when needed. Native Windows is not covered.

## Illumination reference

Use the host's built-in image editor when available. Inspect the original first. Adapt this prompt to the actual light problem:

> Edit this exact documentary photograph as an illumination reference. Balance the people and environment through local exposure, contrast and color. Reduce [specific glare, halo or projected spill] while retaining plausible light direction and luminous lamp cores. Preserve the complete frame and perspective. Keep every person, identity, facial feature, expression, hair strand, hand, garment, readable text, logo and object. Do not reshape, replace faces, beautify, add details, crop, straighten or change geometry. The result is a lighting reference; no generated texture will be delivered.

Keep the original and reference in separate files. Matching aspect ratio is required. Check that the reference's light is useful even if some generated details drift. Grossly shifted people or geometry make a reference unsuitable. Model/version/seed controls depend on the host; do not claim controls or usage numbers the tool does not expose.

## Lighting commands

```bash
/path/to/skill/run.sh light \
  --source /photos/original.png \
  --reference /work/lighting-reference.png \
  --output-stem /work/v2/light \
  --config /work/scene.json
```

`--config` is optional. Source, reference and output must be distinct. Outputs are `.png`, `.jpg`, `.field.npz` and a JSON receipt. A matching source, reference, config, implementation and model hash resumes only if both exports still match their saved hashes. Changed inputs require a new output stem. Receipts record effective face protection regions and clipped source pixels in them.

Example scene config, with normalized `[left, top, right, bottom]` coordinates:

```json
{
  "strength": 1.0,
  "emitter_regions": [[0.30, 0.00, 0.47, 0.17]],
  "regions": [{"xyxy": [0.00, 0.35, 1.00, 1.00], "strength": 0.85, "feather": 0.06}]
}
```

Mark actual lamps/screens after viewing each photo. An emitter rectangle increases white protection only for its brightest pixels. It is not a global exclusion region. Reduce regional strength for a screen that turns muddy or faces that become flat. Keep the medium-scale layer away from identity regions. Explicit `identity_regions` can supply face rectangles when automatic detection misses a face. Set `auto_identity: false` only when those regions have been manually reviewed or the image has no people.

V2 defaults use full transfer strength, a broader gain range, less blanket white protection and an optional medium lighting layer. They are starting points. Judge final image quality rather than choosing the darkest ceiling or the strongest numerical change. Source coordinates are never warped, but lighting can still change the apparent contrast of facial features.

Batch manifest:

```json
{"jobs": [{"id": "01", "source": "/photos/original.png", "reference": "/work/reference.png", "output_stem": "/work/01/light", "config": {}}]}
```

Run `run.sh light --jobs /work/jobs.json`. A batch receipt is saved next to the manifest. Detailed processing is local after reference creation. The model reference is filtered in linear light; only gain fields, never reference texture, are applied to original-resolution source pixels.

## Projected stripes and identity

Past failures showed two distinct problems: whole-image generative edits replaced faces, while a very smooth light field left narrow projected letters intact. Global white protection also preserved some unwanted bright stripes. These failures motivate separate emitter protection, face protection and localized source-light repair.

For a localized stripe, prepare an original-size grayscale mask from the source, white only over the unwanted illumination and black elsewhere. Review its face boundaries. Add:

```json
{"artifact_mask": "/work/stripe-mask.png", "artifact_strength": 0.7, "artifact_radius": 9}
```

This opt-in path interpolates a smoothed log-illumination base from neighboring source pixels and applies the resulting bounded gain. It does not paste model pixels or warp geometry. It can nevertheless flatten shading or exaggerate noise, especially across an eye, glasses or a clothing edge. Inspect those regions at source scale. Do not use this on a broad face-shaped area to simulate face reconstruction. Broad masks over half the image are rejected; that is a guard, not a quality criterion.

Clipped channels contain no recoverable original texture. A white projected stripe crossing an eye may remain partly visible after conservative repair. Report that result as limited, not as a recovered identity. Adding identity references to a generative editor did not reliably solve this failure. Do not replace an original face with a plausible new face. Preserve signage content that belongs to the scene; mask spill on people rather than deleting the event's projection.

## Natural multi-face finish

Use lighting PNGs as inputs, with plain filename stems:

```json
{"jobs": [{"source": "/work/01/light.png", "stem": "01-final"}]}
```

```bash
/path/to/skill/run.sh beauty --manifest /work/beauty.json \
  --output /work/final-v2 --strength 0.3
```

Each result includes PNG/JPEG, a skin-mask PNG and a receipt. The independently implemented CPU backend runs the attributed face detector, skin segmenter and retouch blend-layer model. A soft oval intersects the skin mask, then excludes eyes/glasses, nose and mouth. The finishing delta suppresses slow color changes and is bounded to 10 code values per channel. This is intentionally subtle. Smaller/low-confidence faces are skipped, rather than upscaled to invent features.

The exact protected-pixel checks compare the final PNG against the lighting PNG, not against the pre-lighting original. Verify source dimensions/hash, PNG decoding, mask boundaries and close-up faces. JPEG recompression changes other pixels and is a convenience export, not the preservation proof.

## Format and failure handling

The current processing path supports 8-bit SDR. EXIF orientation is applied before dimensions are measured; ICC-tagged input is converted to sRGB. Untagged RGB is interpreted as sRGB and recorded. HEIC with high bit depth, HDR transfer characteristics or unsupported wide-gamut NCLX is rejected for explicit development instead of silently dropping range. A JPEG with a visible “RAW” badge is still a JPEG.

Never overwrite originals or earlier approved renders. Broken/mismatched cached outputs fail instead of being trusted. Failed artifact masks, aspect-ratio changes, missing weights or failed model checks require correction. Image quality problems remain visual-review failures even when software checks pass.

## Resource use

Local ONNX inference uses CPU, with no LLM tokens by itself. Agent operation, visual review and image-model calls can consume account allowance. Model downloads total about 265 MB, cached once and SHA-256 checked. Reuse the accepted reference and lighting render when changing only beauty strength. Keep full local receipts, summarize normal results, and inspect exceptions. Do not reduce model quality, input resolution or the final visual checks to save tokens. A short new production chat can carry this skill and source files without the entire development history.
