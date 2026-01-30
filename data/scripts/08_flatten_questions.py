#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Flatten categorized questions JSON into a CSV for bulk import.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _default_input_path() -> Path:
    data_root = Path(__file__).resolve().parents[1]
    return data_root / "第一轮仔细清洗" / "第二轮.json"


def _default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_flat.csv")


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_questions(data):
    if isinstance(data, dict):
        category_root = data.get("categories")
        if isinstance(category_root, dict):
            for category, payload in category_root.items():
                if isinstance(payload, dict):
                    questions = payload.get("questions") or []
                elif isinstance(payload, list):
                    questions = payload
                else:
                    questions = []
                for q in questions:
                    if isinstance(q, str):
                        text = q.strip()
                        if text:
                            yield category, text
            return
        for category, payload in data.items():
            if isinstance(payload, dict):
                questions = payload.get("questions") or []
            elif isinstance(payload, list):
                questions = payload
            else:
                questions = []
            for q in questions:
                if isinstance(q, str):
                    text = q.strip()
                    if text:
                        yield category, text
    elif isinstance(data, list):
        for q in data:
            if isinstance(q, str):
                text = q.strip()
                if text:
                    yield "未分类", text


def main() -> int:
    parser = argparse.ArgumentParser(description="Flatten questions JSON into CSV.")
    parser.add_argument(
        "--input",
        dest="input_path",
        type=Path,
        default=_default_input_path(),
        help="Path to the questions JSON file.",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        default=None,
        help="Path to output CSV file.",
    )
    args = parser.parse_args()

    input_path = args.input_path
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    output_path = args.output_path or _default_output_path(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = _load_json(input_path)
    rows = list(_iter_questions(data))

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "question"])
        writer.writerows(rows)

    print(f"rows: {len(rows)} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
