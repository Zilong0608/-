# -*- coding: utf-8 -*-
"""
Export interview questions from chunk files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger


def _default_input(root_dir: Path) -> Path:
    llm_path = root_dir / "data_chunks" / "chunks_llm.json"
    if llm_path.exists():
        return llm_path
    return root_dir / "data_chunks" / "chunks.json"


def _load_chunks(path: Path) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export questions from chunk files")
    parser.add_argument("--input", default="", help="Path to chunks json")
    parser.add_argument("--output", default="", help="Output JSON path")
    args = parser.parse_args()

    config = get_config()
    logger = setup_logger(
        name="export_questions",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    input_path = Path(args.input) if args.input else _default_input(config.paths.root_dir)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        return 1

    output_path = Path(args.output) if args.output else (config.paths.data_reports / "questions.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chunks = _load_chunks(input_path)
    questions: List[str] = []
    for chunk in chunks:
        question = (chunk.get("question") or "").strip()
        if question:
            questions.append(question)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    logger.info("Questions exported: %d", len(questions))
    logger.info("Output: %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
