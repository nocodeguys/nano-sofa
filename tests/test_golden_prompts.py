"""Golden prompts — the exact text, reference list and system instruction
each engine would send for every case in scripts/eval_cases.py.

Why: the existing tests assert substrings, so a paragraph can move from the
top of the prompt to the bottom, a reference can be added, or an engine can
silently drop the system instruction, and nothing fails. These snapshots
make every such change visible in the diff and force a deliberate update:

    .venv/bin/pytest tests/test_golden_prompts.py --update-golden

Review the diff of tests/golden/ before committing the update — that diff IS
the prompt change.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import eval_cases  # noqa: E402

GOLDEN_DIR = REPO_ROOT / "tests" / "golden"


def _golden_path(case_id: str) -> Path:
    return GOLDEN_DIR / f"{case_id}.txt"


def _actual(case: eval_cases.Case, base_image: Path) -> str:
    base = None if case.freeform else base_image
    req = eval_cases.build_request(case, base)
    rendered = eval_cases.render(case, req, base)
    return eval_cases.golden_text(case, req, rendered)


@pytest.mark.parametrize("case", eval_cases.CASES, ids=[c.id for c in eval_cases.CASES])
def test_golden_prompt(server, base_image, case, update_golden):
    actual = _actual(case, base_image)
    path = _golden_path(case.id)

    if update_golden:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return

    assert path.exists(), (
        f"no golden for {case.id} — run pytest --update-golden and review the new file"
    )
    expected = path.read_text(encoding="utf-8")
    if actual != expected:
        diff = "\n".join(difflib.unified_diff(
            expected.splitlines(), actual.splitlines(),
            fromfile=f"golden/{case.id}.txt", tofile="actual", lineterm="", n=2,
        ))
        pytest.fail(
            f"prompt for {case.id} changed. If intended: pytest --update-golden "
            f"and commit the golden diff.\n{diff}"
        )


def test_no_orphan_goldens():
    """A golden without a case is a stale snapshot nobody checks."""
    if not GOLDEN_DIR.exists():
        pytest.skip("no goldens yet")
    known = {c.id for c in eval_cases.CASES}
    orphans = sorted(p.stem for p in GOLDEN_DIR.glob("*.txt") if p.stem not in known)
    assert not orphans, f"goldens without a case: {orphans}"


def test_engines_read_the_same_words(server, base_image):
    """Gemini gets the persona as system instruction and the prompt as the
    user turn; OpenAI has no system field, so it gets the same persona as
    the first paragraph of the same prompt. Either way the model reads the
    same words in the same order."""
    for kind in eval_cases.PRODUCTS:
        for mode in eval_cases.MODES:
            g = eval_cases.CASE_BY_ID[f"{kind}-{mode}-hero-gemini"]
            o = eval_cases.CASE_BY_ID[f"{kind}-{mode}-hero-openai"]
            pg = eval_cases.render(g, eval_cases.build_request(g, base_image), base_image)
            po = eval_cases.render(o, eval_cases.build_request(o, base_image), base_image)
            assert pg.system_instruction.strip(), "Gemini persona missing"
            expected = f"{pg.system_instruction.strip()}\n\n{pg.prompt}"
            mat = eval_cases.PRODUCTS[kind][0]
            if mat == "boucle":
                # The one deliberate dialect difference: GPT Image exaggerates
                # looped fabrics, so it gets the restrained bouclé wording
                # (A/B 2026-09-29). Everything outside those paragraphs matches.
                assert "SCALE AND CONTRAST LIMIT" in po.prompt
                assert "SCALE AND CONTRAST LIMIT" not in pg.prompt
                assert po.prompt.split("\nMATERIAL TEXTURE AUTHORITY")[0] == \
                    expected.split("\nMATERIAL TEXTURE AUTHORITY")[0]
            else:
                assert po.prompt == expected, f"{kind}/{mode}: engines diverge on the words sent"
