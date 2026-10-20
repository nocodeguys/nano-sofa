# Evaluation harness (phase 0 of the predictability refactor)

Two layers, both driven by the same fixed matrix in `scripts/eval_cases.py`:

| Layer | What it pins | Runs where | Cost |
|---|---|---|---|
| Golden prompts (`tests/test_golden_prompts.py`, `tests/golden/*.txt`) | exact prompt text, attached references in order, system instruction, per engine and mode | pytest, CI | free |
| Eval matrix (`scripts/eval_matrix.py` + `scripts/eval_report.py`) | the renders themselves: colour ΔE, product size in frame, backdrop tone | by hand, needs an API key | ~12 images per run |

## The matrix

`scripts/eval_cases.py` — 12 product requests (bed/cremona/taupe and
sofa/boucle/greige × catalog/lifestyle × hero/close_up/detail_fabric) per
engine, one "what the wizard posts today" case, one editorial brief.
Requests are built through the real `_build_generation_request`, so they
exercise the same mapping tables the app uses.

## Golden prompts

```bash
.venv/bin/pytest tests/test_golden_prompts.py
```

Fails with a unified diff when any case's prompt, reference list or system
instruction changes. If the change is intended:

```bash
.venv/bin/pytest tests/test_golden_prompts.py --update-golden
```

then review `git diff tests/golden/` — that diff is the prompt change, and it
belongs in the same PR as the code. Each golden's header carries shape stats
(`chars`, `camera_offset_pct` …) so you can see at a glance whether the
framing instruction moved up or down the prompt.

## Eval matrix

```bash
# inspect without calling anything
.venv/bin/python scripts/eval_matrix.py --dry-run

# real run — key from GEMINI_API_KEY / OPENAI_API_KEY (env or .env)
.venv/bin/python scripts/eval_matrix.py --model gemini-3.1-flash-image --run baseline-main
.venv/bin/python scripts/eval_matrix.py --model gpt-image-2.5-flare --quality xhigh --run baseline-gpt

# measure, then compare two runs
.venv/bin/python scripts/eval_report.py report  outputs/eval/baseline-main
.venv/bin/python scripts/eval_report.py report  outputs/eval/after-phase2
.venv/bin/python scripts/eval_report.py compare outputs/eval/baseline-main outputs/eval/after-phase2
```

Base photos: the bed defaults to an existing upload under `outputs/v2-uploads/`;
pass `--base-sofa` for the sofa cases (they are skipped without it). Use the
same base photos for every run you intend to compare.

### Metrics

- **uph ΔE** — CIEDE2000 between the target hex and the product's dominant
  colour cluster nearest that hex. ≤ 3 indistinguishable, ≤ 6 close, > 10
  visibly wrong. `uph share` says how much of the product that cluster is.
- **width** — product bounding box over frame width. The catalog framing
  contract asks for 0.78–0.84 on a hero.
- **mask** — product pixels over the frame. Close-up ≥ 0.6, macro ≥ 0.9.
- **bd ΔE** — border colour vs the expected backdrop hex (catalog runs only).

The product mask is "not the backdrop", so it is exact on packshots and only
indicative on lifestyle scenes.

### Rules

1. Run the matrix on the **same model** before and after a prompt change.
   Changing the model and the prompt in one run tells you nothing.
2. A phase PR links its `report.md` and the `compare-*.md` against baseline.
3. Expand the matrix only by adding a case to `eval_cases.py`; never by
   hand-editing a golden.
