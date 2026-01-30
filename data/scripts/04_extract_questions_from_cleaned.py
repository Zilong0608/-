# -*- coding: utf-8 -*-
"""
Extract interview questions from cleaned data (no answers).
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
from src.extractors import ExtractorFactory
from src.parsers import QAParser
from src.utils import FileScanner, setup_logger, clean_extracted_text, text_to_markdown


def _extract_questions(text: str, qa_parser: QAParser) -> List[str]:
    if not text or not text.strip():
        return []

    text = qa_parser._normalize_text(text)
    question_positions = []
    for pattern in qa_parser.question_patterns:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups) >= 2:
                question_text = groups[1].strip()
            else:
                question_text = groups[0].strip() if groups else ""
            if qa_parser.step_marker_pattern.match(question_text):
                continue
            question_positions.append({
                "start": match.start(),
                "end": match.end(),
                "question": match.group(0).strip(),
                "question_text": question_text,
            })

    if not question_positions:
        return []

    question_positions.sort(key=lambda x: x["start"])
    unique_positions = []
    last_end = -1
    for pos in question_positions:
        if pos["start"] >= last_end:
            unique_positions.append(pos)
            last_end = pos["end"]

    questions = []
    for pos in unique_positions:
        question = pos["question_text"] or pos["question"]
        question = question.strip()
        if question:
            questions.append(question)
    return questions


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract questions from cleaned data")
    parser.add_argument("--root", default="", help="Root directory of cleaned data")
    parser.add_argument("--output", default="", help="Output JSON path")
    parser.add_argument("--min-length", type=int, default=0, help="Minimum question length")
    parser.add_argument("--dedup", action="store_true", help="Deduplicate questions")
    parser.add_argument("--max-files", type=int, default=0, help="Limit number of files")
    args = parser.parse_args()

    config = get_config()
    logger = setup_logger(
        name="extract_questions",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    root_dir = Path(args.root) if args.root else (config.paths.root_dir / "清洗后数据")
    if not root_dir.exists():
        logger.error("Root directory not found: %s", root_dir)
        return 1

    output_path = Path(args.output) if args.output else (config.paths.data_reports / "questions_only.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scanner = FileScanner(
        root_dir=root_dir,
        supported_formats=config.extractor.supported_formats,
        ocr_formats=config.extractor.ocr_formats,
    )
    files = scanner.scan()
    if args.max_files and args.max_files > 0:
        files = files[:args.max_files]

    extractor_factory = ExtractorFactory(config.extractor)
    qa_parser = QAParser(config.chunker)

    questions: List[str] = []
    processed = 0
    skipped = 0

    for file_info in files:
        if file_info.is_template:
            skipped += 1
            continue
        if not extractor_factory.can_extract(file_info.path):
            skipped += 1
            continue

        doc = extractor_factory.extract(file_info.path)
        if doc.has_errors or doc.is_empty:
            skipped += 1
            continue

        cleaned = clean_extracted_text(doc.full_text)
        content_text = text_to_markdown(cleaned) or cleaned
        file_questions = _extract_questions(content_text, qa_parser)

        if args.min_length:
            file_questions = [q for q in file_questions if len(q) >= args.min_length]

        if file_questions:
            questions.extend(file_questions)

        processed += 1
        if processed % 50 == 0:
            logger.info("Processed %d files, questions: %d", processed, len(questions))

    if args.dedup:
        seen = set()
        deduped = []
        for q in questions:
            if q in seen:
                continue
            seen.add(q)
            deduped.append(q)
        questions = deduped

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    logger.info("Files processed: %d", processed)
    logger.info("Files skipped: %d", skipped)
    logger.info("Questions exported: %d", len(questions))
    logger.info("Output: %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
