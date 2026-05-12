# Scene reference images

This directory holds curated reference images that lock the *look* of a backdrop
or lifestyle environment at pixel level. The text-only env profile (defined in
`server.py:_CYCLORAMA_PROFILES`) gets you 80–90% of the way; a reference image
pins the remaining 10–20%.

## How it's wired

`server.py` looks for a file at `app-v2/scene-references/<env_id>.jpg` (or
`.png`, `.jpeg`) whenever a render is dispatched in **packshot mode**. If found,
it's attached as `scene_reference_image` on the anchor `GenerationRequest` and
the generator emits a `BACKDROP / CYCLORAMA REFERENCE` paragraph instructing the
model to copy backdrop characteristics (tone, top-light gradient, shadow
quality, floor blend) from the reference.

Variants 2..N in a Fotosesja batch don't re-attach the reference — they use the
anchor render itself as a swatch reference, so the cyclorama look propagates
through the anchor automatically.

If a file isn't present for the active env_id, the prompt falls back to the
text-only profile cleanly (no error, just looser scene lock).

## Expected filenames

| env_id                  | filename to save                |
| ----------------------- | ------------------------------- |
| `cyclorama_warm`        | `cyclorama_warm.jpg`            |
| `cyclorama_neutral`     | `cyclorama_neutral.jpg`         |
| `cyclorama_grey`        | `cyclorama_grey.jpg`            |
| `cyclorama_transparent` | (no reference — alpha output)   |

## What makes a good reference

- A single product photographed against the target cyclorama — the *backdrop*
  is what we want the model to copy, not the product.
- Visible top-down lighting gradient on the backdrop (subtle but present).
- Anchored contact shadow (no directional throw).
- No props, no horizon line, no other furniture.
- 1024–2048px on the long edge is plenty.
