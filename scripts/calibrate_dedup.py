from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import yaml

# classifier signature: (text_a, text_b, same_page) -> "STRONG" | "SOFT" | "none"
Classifier = Callable[[str, str, bool], str]


def evaluate(pairs: list[dict], classify: Classifier) -> dict[str, float]:
    """Compare a classifier's output to the labeled corpus.

    false_positive: predicted a match (STRONG/SOFT) where expected was none.
    false_negative: predicted none where a match was expected.
    """
    fp = fn = 0
    for p in pairs:
        predicted = classify(p["a"], p["b"], p["same_page"])
        expected = p["expected"]
        pred_match = predicted != "none"
        exp_match = expected != "none"
        if pred_match and not exp_match:
            fp += 1
        if exp_match and not pred_match:
            fn += 1
    total = len(pairs) or 1
    return {
        "total": total,
        "false_positive": fp,
        "false_negative": fn,
        "false_positive_rate": fp / total,
        "false_negative_rate": fn / total,
    }


def _main() -> int:  # pragma: no cover — manual calibration tool
    corpus = Path(__file__).parent.parent / "tests" / "knowledge" / "golden_corpus.yaml"
    pairs = yaml.safe_load(corpus.read_text(encoding="utf-8"))
    from knowledge.dedup import cosine
    from knowledge.embedder import Embedder, openai_embed_fn
    import os

    embed_fn = openai_embed_fn("text-embedding-3-small", os.environ["OPENAI_API_KEY"])
    embedder = Embedder("text-embedding-3-small", embed_fn)
    strong = float(os.getenv("KNOWLEDGE_STRONG_THRESHOLD", "0.82"))
    soft = float(os.getenv("KNOWLEDGE_SOFT_THRESHOLD", "0.68"))

    def classify(a: str, b: str, same_page: bool) -> str:
        va, vb = embedder.embed([a, b])
        score = cosine(va, vb)
        if same_page and score >= strong:
            return "STRONG"
        if not same_page and score >= soft:
            return "SOFT"
        return "none"

    result = evaluate(pairs, classify)
    print(f"thresholds: strong={strong} soft={soft}")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
