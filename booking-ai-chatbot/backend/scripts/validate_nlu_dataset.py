"""Validate NLU JSONL artifacts. Exits non-zero on any contract violation."""

# ruff: noqa: E501, E702

from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nlu"
FILES = ["utterances.jsonl", "train.jsonl", "validation.jsonl", "test.jsonl", "golden_test.jsonl", "hard_negatives.jsonl", "out_of_scope.jsonl", "ambiguous_cases.jsonl", "multi_intent_cases.jsonl"]
STATES = {"IDLE", "SELECTING_SHOP", "SELECTING_DATE", "SELECTING_PEOPLE", "SELECTING_DURATION", "SELECTING_SERVICE", "SELECTING_TIME", "SELECTING_THERAPIST", "COLLECTING_PHONE", "VERIFYING_PHONE", "AWAITING_CONFIRMATION", "BOOKING_EXECUTING", "COMPLETED", "BOOKING_FAILED", "CANCELLED"}


def normalized(text: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn").replace("đ", "d").split())


def load(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path.name}:{line_no}: invalid JSON: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_no}: record must be an object")
        rows.append(value)
    return rows


def main() -> int:
    errors: list[str] = []
    catalog = json.loads((DATA / "intent_catalog.yaml").read_text(encoding="utf-8"))
    intents = {item["intent"] for item in catalog["intents"]}
    sets = {name: load(DATA / name) for name in FILES}
    for name, rows in sets.items():
        ids: set[str] = set(); texts: dict[str, str] = {}
        for row in rows:
            rid, text = row.get("id"), row.get("text")
            if not isinstance(rid, str) or not rid or rid in ids:
                errors.append(f"{name}: missing/duplicate id {rid!r}")
            ids.add(str(rid))
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{name}:{rid}: empty text"); continue
            norm = normalized(text)
            if norm in texts:
                errors.append(f"{name}:{rid}: normalized duplicate of {texts[norm]}")
            texts[norm] = str(rid)
            if row.get("intent") not in intents:
                errors.append(f"{name}:{rid}: unknown intent {row.get('intent')}")
            if row.get("current_state") not in STATES:
                errors.append(f"{name}:{rid}: unknown state {row.get('current_state')}")
            for entity in row.get("entities", []):
                start, end, value = entity.get("start"), entity.get("end"), entity.get("value")
                if not isinstance(start, int) or not isinstance(end, int) or text[start:end] != value:
                    errors.append(f"{name}:{rid}: invalid entity offset {entity}")
                if entity.get("type") in {"shop_name", "service_name", "therapist_name"} and entity.get("id"):
                    errors.append(f"{name}:{rid}: mutable business entity must not embed an ID")
    positives = sets["utterances.jsonl"]
    counts = Counter(row["intent"] for row in positives)
    for intent in intents:
        if counts[intent] < 40:
            errors.append(f"utterances.jsonl: {intent} has {counts[intent]} positives; minimum is 40")
    split_rows = sets["train.jsonl"] + sets["validation.jsonl"] + sets["test.jsonl"]
    groups: dict[str, str] = {}
    for row in split_rows:
        group, split = row.get("template_group"), row.get("split")
        previous = groups.setdefault(str(group), str(split))
        if previous != split:
            errors.append(f"split leakage: template group {group} appears in {previous} and {split}")
    total = len(split_rows)
    ratios = Counter(row["split"] for row in split_rows)
    expected = {"train": .70, "validation": .15, "test": .15}
    for split, target in expected.items():
        actual = ratios[split] / total
        if abs(actual - target) > .04:
            errors.append(f"split ratio {split}={actual:.3f}, expected {target:.2f}±.04")
    golden = sets["golden_test.jsonl"]
    if len(golden) < 960:
        errors.append(f"golden_test.jsonl: {len(golden)} records; minimum is 960")
    required = {"tôi muốn đặt cửa hàng Komorebi Ba Đình", "Komorebi Ba Đình", "cho tôi chi nhánh ba dinh", "tôi chọn số 6", "cửa hàng thứ sáu", "không phải Bình Thạnh, đổi sang Ba Đình", "Ba Đình nhé", "chỗ Ba Đình lúc nãy", "Ba Đình còn giờ nào?", "địa chỉ Ba Đình ở đâu?"}
    missing = required - {row["text"] for row in golden}
    if missing:
        errors.append(f"golden_test.jsonl: missing mandatory examples: {sorted(missing)}")
    report = {"valid": not errors, "files": {name: len(rows) for name, rows in sets.items()}, "positive_counts": counts, "split_counts": ratios, "errors": errors}
    (DATA / "validation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=dict))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
