# -*- coding: utf-8 -*-
"""
Step 0: classify raw files into categories and optionally move them.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import FileScanner, setup_logger, is_resume_template


CATEGORY_NAMES = {
    "question": "题库",
    "experience": "经验",
    "template": "模板",
    "other": "其他",
}

CATEGORY_DIRS = set(CATEGORY_NAMES.values())

QUESTION_KEYWORDS = [
    "面试题", "题库", "题目", "真题", "八股文", "刷题", "笔试", "练习题",
    "专项练习", "题单", "问答", "题解", "题汇总", "面试问答",
]

EXPERIENCE_KEYWORDS = [
    "面经", "经验", "心得", "复盘", "技巧", "指南", "攻略",
    "流程", "建议", "要点", "注意事项", "方法论", "准备",
]

TEMPLATE_KEYWORDS = [
    "简历", "模板", "resume", "cv", "自荐信", "应聘登记表", "个人信息表",
]


@dataclass
class ClassificationResult:
    source_path: Path
    category: str
    confidence: float
    reasons: List[str]
    dest_path: Path

    def to_dict(self) -> dict:
        return {
            "source_path": str(self.source_path),
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "reasons": ", ".join(self.reasons),
            "dest_path": str(self.dest_path),
        }


def _normalize_path(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _score_keywords(text: str, keywords: List[str], weight: int) -> Tuple[int, List[str]]:
    hits = [kw for kw in keywords if kw in text]
    return len(hits) * weight, hits


def _load_text_samples(path: Path, max_chars: int = 4000) -> Dict[str, str]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        docs = json.load(f)
    samples = {}
    for doc in docs:
        source = doc.get("source_path")
        if not source:
            continue
        text = doc.get("markdown_text") or doc.get("full_text") or ""
        text = text.strip()
        if not text:
            continue
        samples[_normalize_path(Path(source))] = text[:max_chars]
    return samples


def _classify_file(
    file_info,
    text_sample: str,
    source_root: Path,
    dest_root: Path,
) -> ClassificationResult:
    rel_path = file_info.path.relative_to(source_root)
    combined = f"{file_info.path} {file_info.name} {file_info.category}".lower()

    reasons: List[str] = []
    if file_info.is_template:
        dest_path = dest_root / CATEGORY_NAMES["template"] / rel_path
        return ClassificationResult(
            source_path=file_info.path,
            category=CATEGORY_NAMES["template"],
            confidence=1.0,
            reasons=["scan_template"],
            dest_path=dest_path,
        )

    template_score, template_hits = _score_keywords(combined, TEMPLATE_KEYWORDS, 3)
    if template_hits:
        reasons.extend([f"path_template:{kw}" for kw in template_hits])

    if text_sample and is_resume_template(file_info.path, text_sample):
        template_score += 5
        reasons.append("text_resume_template")

    question_score, question_hits = _score_keywords(combined, QUESTION_KEYWORDS, 2)
    if question_hits:
        reasons.extend([f"path_question:{kw}" for kw in question_hits])

    experience_score, experience_hits = _score_keywords(combined, EXPERIENCE_KEYWORDS, 2)
    if experience_hits:
        reasons.extend([f"path_experience:{kw}" for kw in experience_hits])

    if text_sample:
        qmarks = text_sample.count("?") + text_sample.count("？")
        if qmarks >= 5:
            question_score += 2
            reasons.append("text_qmarks")
        if "问题" in text_sample and "答案" in text_sample:
            question_score += 3
            reasons.append("text_qa_pair")
        if any(kw in text_sample for kw in EXPERIENCE_KEYWORDS):
            experience_score += 1
            reasons.append("text_experience_kw")

    scores = {
        CATEGORY_NAMES["template"]: template_score,
        CATEGORY_NAMES["question"]: question_score,
        CATEGORY_NAMES["experience"]: experience_score,
    }

    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]
    total_score = sum(scores.values())
    confidence = (best_score / total_score) if total_score else 0.0

    if best_score == 0:
        best_category = CATEGORY_NAMES["other"]

    dest_path = dest_root / best_category / rel_path
    return ClassificationResult(
        source_path=file_info.path,
        category=best_category,
        confidence=confidence,
        reasons=reasons if reasons else ["no_match"],
        dest_path=dest_path,
    )


def _resolve_conflict(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    idx = 1
    while True:
        candidate = parent / f"{stem}__dup{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def main():
    parser = argparse.ArgumentParser(description="Classify raw files into categories.")
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files into category folders (default is dry-run).",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files into category folders (default is dry-run).",
    )
    parser.add_argument(
        "--dest-root",
        type=str,
        default="",
        help="Override destination root (default is data_raw).",
    )
    args = parser.parse_args()

    config = get_config()
    logger = setup_logger(
        name="classify_files",
        log_dir=config.paths.logs_dir,
        console_output=True,
    )

    if args.move and args.copy:
        raise ValueError("Use only one of --move or --copy.")

    dest_root = Path(args.dest_root).resolve() if args.dest_root else config.paths.data_raw
    skip_classified = dest_root.resolve() == config.paths.data_raw.resolve()
    mode = "move" if args.move else ("copy" if args.copy else "dry-run")
    logger.info("=" * 50)
    logger.info("Step 0: classify files")
    logger.info(f"Source root: {config.paths.data_raw}")
    logger.info(f"Destination root: {dest_root}")
    logger.info(f"Mode: {mode}")
    logger.info("=" * 50)

    scan_result_path = config.paths.data_reports / "scan_result.json"
    if scan_result_path.exists():
        files, _stats = FileScanner.load_scan_result(scan_result_path)
        logger.info(f"Loaded scan result: {len(files)} files")
    else:
        ocr_formats = config.extractor.ocr_formats if config.extractor.enable_ocr else []
        scanner = FileScanner(
            root_dir=config.paths.data_raw,
            supported_formats=config.extractor.supported_formats,
            ocr_formats=ocr_formats,
        )
        files = scanner.scan()
        scanner.save_scan_result(files, scan_result_path)
        logger.info(f"Scanned {len(files)} files")

    text_samples = _load_text_samples(config.paths.data_ingest / "extracted_documents.json")
    if text_samples:
        logger.info(f"Loaded text samples: {len(text_samples)}")
    else:
        logger.info("No extracted text samples found, using path-only heuristics")

    results: List[ClassificationResult] = []
    skipped = 0
    for file_info in files:
        rel_path = file_info.path.relative_to(config.paths.data_raw)
        if skip_classified and rel_path.parts and rel_path.parts[0] in CATEGORY_DIRS:
            skipped += 1
            continue

        sample = text_samples.get(_normalize_path(file_info.path), "")
        result = _classify_file(file_info, sample, config.paths.data_raw, dest_root)
        results.append(result)

    counts = {}
    for r in results:
        counts[r.category] = counts.get(r.category, 0) + 1

    report_dir = config.paths.data_reports
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "classification_result.json"
    csv_path = report_dir / "classification_result.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in results], f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["source_path", "category", "confidence", "reasons", "dest_path"],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())

    logger.info("Classification summary:")
    for category, count in sorted(counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {category}: {count}")
    logger.info(f"Skipped already-classified: {skipped}")
    logger.info(f"Report saved: {json_path}")
    logger.info(f"Report saved: {csv_path}")

    if not args.move and not args.copy:
        logger.info("Dry-run complete. Use --move or --copy to apply changes.")
        return

    moved = 0
    missing = 0
    failed = 0
    for r in results:
        if not r.source_path.exists():
            missing += 1
            continue
        try:
            dest = _resolve_conflict(r.dest_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if args.copy:
                shutil.copy2(str(r.source_path), str(dest))
            else:
                shutil.move(str(r.source_path), str(dest))
            moved += 1
        except Exception as exc:
            failed += 1
            logger.warning(f"Action failed: {r.source_path} -> {r.dest_path} ({exc})")
    action_label = "Copied" if args.copy else "Moved"
    logger.info(f"{action_label} files: {moved}")
    logger.info(f"Missing source files: {missing}")
    logger.info(f"Action failures: {failed}")


if __name__ == "__main__":
    main()
