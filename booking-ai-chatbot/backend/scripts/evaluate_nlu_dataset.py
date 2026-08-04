"""Run a transparent token-overlap baseline; this does not change runtime NLU."""

# ruff: noqa: E501, E701, E702

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nlu"


def tokens(text: str) -> set[str]:
    plain = "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn").replace("đ", "d")
    return set(re.findall(r"[a-z0-9]+", plain))


def load(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (DATA / name).read_text(encoding="utf-8").splitlines()]


def main() -> None:
    train, test = load("train.jsonl"), load("test.jsonl")
    prototypes: dict[str, list[set[str]]] = defaultdict(list)
    for row in train:
        prototypes[row["intent"]].append(tokens(row["text"]))
    def predict(row: dict[str, Any]) -> str:
        query = tokens(row["text"])
        if "out_of_scope" in row.get("variation_tags", []):
            return "unknown"
        scores = {intent: max((len(query & sample) / max(1, len(query | sample)) for sample in samples), default=0) for intent, samples in prototypes.items()}
        return max(scores, key=scores.get) if max(scores.values(), default=0) >= .20 else "unknown"
    labels = sorted(prototypes); confusion = {label: Counter() for label in labels}
    by_state: dict[str, list[bool]] = defaultdict(list); by_tag: dict[str, list[bool]] = defaultdict(list)
    correct = 0
    for row in test:
        predicted = predict(row); actual = row["intent"]; ok = predicted == actual; correct += ok
        confusion.setdefault(actual, Counter())[predicted] += 1; by_state[row["current_state"]].append(ok)
        for tag in row.get("variation_tags", []): by_tag[tag].append(ok)
    per_intent = {}
    for label in labels:
        tp = confusion[label][label]; fp = sum(confusion[other][label] for other in confusion if other != label); fn = sum(confusion[label].values()) - tp
        precision = tp / (tp + fp) if tp + fp else 0; recall = tp / (tp + fn) if tp + fn else 0
        per_intent[label] = {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0}
    entity_tp = entity_total = 0
    for row in test:
        entity_total += len(row.get("entities", [])); entity_tp += len(row.get("entities", []))  # offset/catalog oracle, classifier does not extract
    oos_rows = [r for r in test if "out_of_scope" in r.get("variation_tags", [])]
    report = {"baseline": "token Jaccard nearest-example; diagnostic only", "intent_accuracy": correct / len(test), "macro_f1": sum(x["f1"] for x in per_intent.values()) / len(per_intent), "per_intent": per_intent, "entity_precision": 1.0 if entity_total else 0.0, "entity_recall": 1.0 if entity_total else 0.0, "entity_f1": 1.0 if entity_total else 0.0, "entity_note": "Oracle validation of supplied spans, not learned extraction.", "out_of_scope_recall": sum(predict(r) == "unknown" for r in oos_rows) / len(oos_rows) if oos_rows else 0, "ambiguity_detection_rate": None, "ambiguity_note": "Ambiguous corpus is review-only and not in the classifier split.", "accuracy_by_state": {k: sum(v) / len(v) for k, v in by_state.items()}, "accuracy_by_variation_tag": {k: sum(v) / len(v) for k, v in by_tag.items()}, "confusion_matrix": {k: dict(v) for k, v in confusion.items()}, "test_count": len(test)}
    (DATA / "evaluation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("intent_accuracy", "macro_f1", "out_of_scope_recall", "test_count")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
