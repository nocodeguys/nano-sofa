# nano-sofa

Local Gradio app that generates furniture product variants (sofas, beds, etc.) using Google's Nano Banana image model, with 3D-rendered leg references for consistent leg swaps across variants.

## Status

Scaffold stage. Five Claude Code subagents are defined under `.claude/agents/` and an initial sofa schema + leg manifest template are in place. Nothing runs yet — the app code, Dockerfile, and leg renders are still owned by their respective agents and produced on demand.

## Repository layout

```
.claude/agents/        # subagent definitions, one per concern
prompts/schemas/       # JSON schemas per product type
prompts/test-matrices/ # eval sets per schema
legs/                  # 3D leg reference library + manifest
legs/source/           # Blender source files (you create these)
docs/research/         # Nano Banana state, refreshed by the researcher agent
app/                   # Gradio app (gradio-app-architect produces this)
data/                  # base product photos (you upload these)
outputs/               # generated images
state/                 # SQLite DB
```

## How to use the agents

Open Claude Code in this directory. The five agents are auto-discovered.

Sequence for first build:

1. `nano-banana-researcher` — produces `docs/research/nano-banana-state.md`.
2. `furniture-prompt-architect` — refines `prompts/schemas/sofa.json` against the research.
3. `leg-pipeline-designer` — produces `legs/render-blender.py` and finalizes the manifest schema.
4. `gradio-app-architect` — builds `app/`.
5. `docker-packager` — produces `Dockerfile`, `docker-compose.yml`, install scripts.

After v1 is shipped, invoke individual agents as concerns arise:

- New product type → `furniture-prompt-architect`
- New leg style → `leg-pipeline-designer` (then onboard via `legs/ADDING-A-LEG.md`)
- New UI feature → `gradio-app-architect`
- Model API changes → `nano-banana-researcher` first, then whichever agent owns the affected layer

## Why this shape

Each agent owns a narrow concern. They share state through files, not conversation. This means changes are reviewable as diffs, agents stay focused, and a non-technical teammate can edit (for example) a JSON schema without touching code.

The three load-bearing decisions:

- **JSON-structured prompts** for batch determinism across variant matrices.
- **3D-rendered leg references** so leg swaps preserve geometry instead of being described in words.
- **Schemas as the contract** between agents — the prompt-architect's output is the gradio-app-architect's input.
