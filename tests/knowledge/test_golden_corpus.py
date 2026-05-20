from __future__ import annotations
from pathlib import Path
import yaml
from scripts.calibrate_dedup import evaluate

CORPUS = Path(__file__).parent / "golden_corpus.yaml"


def test_corpus_is_well_formed():
    pairs = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    assert len(pairs) >= 15
    for p in pairs:
        assert set(p) >= {"a", "b", "same_page", "expected"}
        assert p["expected"] in ("STRONG", "SOFT", "none")


def test_evaluate_returns_rates():
    # a perfect classifier returning the labeled answer scores zero error
    pairs = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    result = evaluate(pairs, classify=lambda a, b, same_page: _label(pairs, a, b))
    assert result["false_positive"] == 0
    assert result["false_negative"] == 0


def _label(pairs, a, b):
    for p in pairs:
        if p["a"] == a and p["b"] == b:
            return p["expected"]
    return "none"
