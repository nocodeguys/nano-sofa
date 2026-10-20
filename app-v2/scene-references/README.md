# Scene reference plates

Curated **empty studio plates** that lock a backdrop's look at pixel level.
The written backdrop paragraph (`backdrops[].prompt_en` in
`app-v2/catalog.json`) gets the model most of the way; the plate pins the
remaining tone, gradient and floor-to-wall blend.

## How it is wired (phase 3, 2026-10-20)

A backdrop entry in `catalog.json` names its plate:

```json
{ "id": "ivory", "plate": "cyclorama_architectural.png", "locks": { … }, "normalize": { … } }
```

`studio/request_builder._scene_reference_path` attaches that file as the
scene reference whenever the chosen background is a **locked** backdrop
(one with a `locks` block). The prompt then carries the `BACKDROP /
CYCLORAMA REFERENCE` paragraph telling the model to take only the backdrop
characteristics from it. Detail / macro shots never get the plate
(`plan_reference_slots` drops it — a whole studio at hero distance pulls a
macro back to a hero).

Backdrops without a plate (paperwhite, neutral, the unlocked warm / grey /
softlight) render from the paragraph alone. Variants 2..N of a set do not
re-attach the plate; the normalized anchor render carries the look.

## Files

| backdrop id | plate                            |
| ----------- | -------------------------------- |
| `ivory`     | `cyclorama_architectural.png`    |
| `atelier`   | `cyclorama_atelier_gradient.png` |
| `softblush` | `cyclorama_softblush.png`        |

To add one: drop the file here and set `plate` on the backdrop entry.

## What makes a good plate

- An **empty** studio against the target cyclorama — no product, no props.
- A visible top-down lighting gradient on the backdrop (subtle but present).
- No horizon line, no other furniture.
- 1024–2048 px on the long edge is plenty.
