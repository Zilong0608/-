# -*- coding: utf-8 -*-
"""
Step 4 (LLM): extract questions only from cleaned question bank files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.extractors import ExtractorFactory
from src.utils import FileScanner, setup_logger, clean_extracted_text, text_to_markdown, is_resume_template


SYSTEM_PROMPT = (
    "You are a strict interview-question extractor. "
    "Return ONLY a JSON array. Each item must be a question string or an object with a 'question' field. "
    "Do NOT include answers. Do NOT add commentary or markdown. "
    "Do NOT treat step headings like 'Step 1/第1步/步骤一' as questions. "
    "Keep question wording intact; remove leading bullets or numbering. "
    "If a line is not a real question, skip it."
)

STEP_HEADING_PATTERN = re.compile(
    r'^(?:'
    r'\u7b2c[\u4e00-\u5341\d]+\u6b65'
    r'|\u6b65\u9aa4\s*[\u4e00-\u5341\d]+'
    r'|step\s*\d+'
    r')',
    re.IGNORECASE
)


def _resolve_root(root_dir: Path, supported_formats: Sequence[str], ocr_formats: Sequence[str]) -> Path:
    candidate = root_dir
    nested = candidate / "题库"
    if not nested.exists():
        return candidate

    suffixes = {s.lower() for s in (list(supported_formats) + list(ocr_formats))}
    for entry in candidate.iterdir():
        if entry.is_file() and entry.suffix.lower() in suffixes:
            return candidate
    return nested


def _append_log(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _group_files_by_folder(files: Sequence[Any], root_dir: Path) -> Dict[str, List[Any]]:
    groups: Dict[str, List[Any]] = {}
    for info in files:
        try:
            rel = info.path.relative_to(root_dir)
            parts = rel.parts
            folder = parts[0] if len(parts) > 1 else root_dir.name
        except ValueError:
            folder = info.category or "未分类"
        groups.setdefault(folder, []).append(info)
    for folder in groups:
        groups[folder] = sorted(groups[folder], key=lambda x: x.path.name)
    return groups


def _safe_filename(name: str) -> str:
    # Windows-invalid characters: <>:"/\\|?*
    return re.sub(r'[<>:"/\\\\|?*]+', "_", name).strip()


def _split_by_paragraphs(text: str, max_chars: int) -> List[str]:
    parts: List[str] = []
    paras = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    current: List[str] = []
    current_len = 0
    for para in paras:
        add_len = len(para) + 2
        if current and current_len + add_len > max_chars:
            parts.append("\n\n".join(current).strip())
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += add_len
    if current:
        parts.append("\n\n".join(current).strip())
    return parts


def split_markdown_sections(text: str, max_chars: int) -> List[str]:
    if not text:
        return []

    lines = text.splitlines()
    sections: List[Tuple[Optional[str], str]] = []
    current_title: Optional[str] = None
    current_lines: List[str] = []

    for line in lines:
        if line.strip().startswith("#"):
            heading_text = line.strip().lstrip("#").strip()
            if STEP_HEADING_PATTERN.match(heading_text):
                current_lines.append(line)
                continue
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))

    if not sections:
        return []

    output: List[str] = []
    for title, body in sections:
        base_text = (title + "\n\n" + body).strip() if title else body.strip()
        if not base_text:
            continue
        if len(base_text) <= max_chars:
            output.append(base_text)
        else:
            prefix = (title + "\n\n") if title else ""
            for part in _split_by_paragraphs(body, max_chars - len(prefix)):
                output.append((prefix + part).strip())
    return [s for s in output if s]


def _call_openai(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    timeout: int,
    base_url: str,
    max_retries: int,
    retry_sleep: float,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    use_max_completion_tokens = model.lower().startswith("gpt-5")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if not use_max_completion_tokens:
        payload["temperature"] = 0
    if use_max_completion_tokens:
        payload["max_completion_tokens"] = max_output_tokens
    else:
        payload["max_tokens"] = max_output_tokens
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            last_error = exc
            if attempt + 1 >= max_retries:
                break
            time.sleep(retry_sleep)
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI request failed with unknown error")


def _extract_json_array(text: str) -> List[Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[\w-]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "questions" in parsed:
            parsed = parsed["questions"]
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return []
    return []


def _normalize_question(question: str) -> str:
    question = re.sub(r'^\s*[-\*\d\.\)\u4e00-\u5341]+[\s、\.]*', '', question).strip()
    question = re.sub(r'\s+', ' ', question).strip()
    return question


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 1.5))


def _extract_questions_from_items(items: Iterable[Any]) -> List[str]:
    questions: List[str] = []
    for item in items:
        if isinstance(item, str):
            q = _normalize_question(item)
        elif isinstance(item, dict):
            q = _normalize_question(str(item.get("question", "")).strip())
        else:
            q = ""
        if q:
            questions.append(q)
    return questions


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM question extractor for question bank")
    parser.add_argument("--root", default="", help="Root directory of question bank")
    parser.add_argument("--output", default="", help="Output JSON path")
    parser.add_argument("--progress-log", default="", help="Progress log path")
    parser.add_argument("--unprocessed-report", default="", help="Unprocessed report JSON path")
    parser.add_argument(
        "--output-format",
        choices=["records", "per-file"],
        default="records",
        help="Output as a single records list or one JSON per source file",
    )
    parser.add_argument("--mode", default="semantic_regroup_theory_only", help="Mode label for per-file JSON")
    parser.add_argument("--model", default="gpt-5-nano-2025-08-07")
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--max-output-tokens", type=int, default=600)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-sections", type=int, default=0)
    parser.add_argument("--min-length", type=int, default=0)
    parser.add_argument("--dedup", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--no-markdown", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-match", default="", help="Only process files whose path contains this substring")
    args = parser.parse_args()

    config = get_config()
    logger = setup_logger(
        name="extract_questions_llm",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not set.")
        return 1
    if not api_key.isascii():
        logger.error("OPENAI_API_KEY contains non-ASCII characters. Please set a valid API key.")
        return 1

    root_dir = Path(args.root) if args.root else (config.paths.root_dir / "清洗后数据" / "题库")
    root_dir = _resolve_root(root_dir, config.extractor.supported_formats, config.extractor.ocr_formats)
    if not root_dir.exists():
        logger.error("Root directory not found: %s", root_dir)
        return 1

    output_path = Path(args.output) if args.output else (config.paths.data_chunks / "questions_llm.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_format = args.output_format
    output_dir: Optional[Path] = None
    if output_format == "per-file":
        if output_path.suffix.lower() == ".json":
            output_dir = output_path.with_suffix("")
        else:
            output_dir = output_path
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Per-file output directory: %s", output_dir)

    progress_log_path = Path(args.progress_log) if args.progress_log else (config.paths.data_reports / "questions_llm_progress.log")
    progress_log_path.parent.mkdir(parents=True, exist_ok=True)
    progress_log_path.write_text("", encoding="utf-8")

    unprocessed_report_path = (
        Path(args.unprocessed_report)
        if args.unprocessed_report
        else (config.paths.data_reports / "questions_llm_unprocessed.json")
    )
    unprocessed_report_path.parent.mkdir(parents=True, exist_ok=True)

    scanner = FileScanner(
        root_dir=root_dir,
        supported_formats=config.extractor.supported_formats,
        ocr_formats=config.extractor.ocr_formats,
    )
    files = scanner.scan()
    if args.source_match:
        key = args.source_match.lower()
        files = [f for f in files if key in str(f.path).lower()]
    if args.max_files and args.max_files > 0:
        files = files[:args.max_files]

    grouped_files = _group_files_by_folder(files, root_dir)
    extractor_factory = ExtractorFactory(config.extractor)

    question_records: List[Dict[str, Any]] = []
    total_questions = 0
    unprocessed: List[Dict[str, Any]] = []
    processed = 0
    skipped = 0
    handled = 0
    total_usage = 0
    est_tokens = 0
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    use_markdown = not args.no_markdown

    file_index = 0
    for folder_name, folder_files in grouped_files.items():
        processed_files: List[str] = []
        skipped_files: List[Dict[str, Any]] = []
        failed_files: List[Dict[str, Any]] = []
        folder_start_count = len(question_records)
        folder_est_tokens = 0

        logger.info("Processing folder: %s (%d files)", folder_name, len(folder_files))

        for file_info in folder_files:
            file_index += 1
            file_question_count = 0
            file_failed = False
            file_error = ""
            file_questions: List[str] = []

            if file_info.is_template:
                skipped += 1
                handled += 1
                skipped_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": "template",
                })
                continue
            if not extractor_factory.can_extract(file_info.path):
                skipped += 1
                handled += 1
                skipped_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": "unsupported",
                })
                continue

            doc = extractor_factory.extract(file_info.path)
            if doc.has_errors or doc.is_empty:
                skipped += 1
                handled += 1
                skipped_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": "extract_failed" if doc.has_errors else "empty",
                })
                continue

            cleaned = clean_extracted_text(doc.full_text or "")
            if is_resume_template(file_info.path, cleaned):
                skipped += 1
                handled += 1
                skipped_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": "resume_template",
                })
                continue

            content_text = text_to_markdown(cleaned) if use_markdown else cleaned
            if not content_text.strip():
                skipped += 1
                handled += 1
                skipped_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": "no_text",
                })
                continue

            sections = split_markdown_sections(content_text, args.max_chars)
            if args.max_sections and args.max_sections > 0:
                sections = sections[:args.max_sections]
            if not sections:
                skipped += 1
                handled += 1
                skipped_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": "no_sections",
                })
                continue

            if args.dry_run:
                folder_est_tokens += sum(_estimate_tokens(s) for s in sections)
                processed += 1
                handled += 1
                processed_files.append(file_info.name)
                continue

            for section_index, section in enumerate(sections, start=1):
                user_prompt = (
                    "Extract interview questions from the text below. "
                    "Return ONLY a JSON array.\n\n"
                    "TEXT:\n" + section
                )
                try:
                    resp = _call_openai(
                        api_key=api_key,
                        model=args.model,
                        system_prompt=SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        max_output_tokens=args.max_output_tokens,
                        timeout=120,
                        base_url=base_url,
                        max_retries=args.retries,
                        retry_sleep=args.retry_sleep,
                    )
                except urllib.error.HTTPError as exc:
                    body = exc.read().decode("utf-8", errors="ignore")
                    file_failed = True
                    file_error = f"http_error: {body[:200]}"
                    logger.error("HTTP error on %s section %d: %s", file_info.name, section_index, body)
                    continue
                except Exception as exc:
                    file_failed = True
                    file_error = f"request_failed: {exc}"
                    logger.error("Request failed on %s section %d: %s", file_info.name, section_index, exc)
                    continue

                usage = resp.get("usage", {})
                total_usage += int(usage.get("total_tokens") or 0)

                content = ""
                try:
                    content = resp["choices"][0]["message"]["content"]
                except Exception:
                    file_failed = True
                    file_error = "no_content"
                    logger.warning("No content in response for %s section %d", file_info.name, section_index)
                    continue

                items = _extract_json_array(content)
                if not items:
                    continue

                questions = _extract_questions_from_items(items)
                if args.min_length:
                    questions = [q for q in questions if len(q) >= args.min_length]

                for question in questions:
                    question_records.append({
                        "id": f"q_{len(question_records) + 1:08d}",
                        "question": question,
                        "source_path": str(file_info.path),
                        "file_name": file_info.name,
                        "category": file_info.category,
                        "section_index": section_index,
                        "file_index": file_index,
                        "metadata": {
                            "llm": True,
                            "model": args.model,
                        },
                    })
                    file_question_count += 1

                if args.sleep:
                    time.sleep(args.sleep)

            if file_question_count > 0:
                processed += 1
                handled += 1
                processed_files.append(file_info.name)
            elif file_failed:
                handled += 1
                failed_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": file_error or "failed",
                })
            else:
                skipped += 1
                handled += 1
                skipped_files.append({
                    "file_name": file_info.name,
                    "source_path": str(file_info.path),
                    "reason": "no_questions",
                })

            if handled % 20 == 0:
                logger.info(
                    "Handled %d files (questions files: %d, skipped: %d), questions: %d",
                    handled,
                    processed,
                    skipped,
                    len(question_records),
                )

        if skipped_files:
            for item in skipped_files:
                unprocessed.append({
                    "folder": folder_name,
                    "status": "skipped",
                    **item,
                })
        if failed_files:
            for item in failed_files:
                unprocessed.append({
                    "folder": folder_name,
                    "status": "failed",
                    **item,
                })

        folder_added = len(question_records) - folder_start_count
        if args.dry_run:
            logger.info("Folder done: %s (dry-run, est tokens: %d)", folder_name, folder_est_tokens)
            _append_log(progress_log_path, f"Folder done: {folder_name} (dry-run, est tokens: {folder_est_tokens})")
        else:
            logger.info("Folder done: %s (files: %d, questions: +%d)", folder_name, len(processed_files), folder_added)
            _append_log(progress_log_path, f"Folder done: {folder_name} (files: {len(processed_files)}, questions: +{folder_added})")

        processed_list = ", ".join(processed_files) if processed_files else "-"
        _append_log(progress_log_path, f"Files: {processed_list}")
        if skipped_files:
            _append_log(progress_log_path, f"Skipped: {len(skipped_files)}")
        if failed_files:
            _append_log(progress_log_path, f"Failed: {len(failed_files)}")
        _append_log(progress_log_path, "-" * 40)

    if args.dry_run:
        logger.info("Files scanned: %d", len(files))
        logger.info("Estimated input tokens: ~%d", est_tokens)
        return 0

    if args.dedup:
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for item in question_records:
            q = item.get("question", "")
            if q in seen:
                continue
            seen.add(q)
            deduped.append(item)
        question_records = deduped

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(question_records, f, ensure_ascii=False, indent=2)

    with open(unprocessed_report_path, "w", encoding="utf-8") as f:
        json.dump(unprocessed, f, ensure_ascii=False, indent=2)

    logger.info("Files processed: %d", processed)
    logger.info("Files skipped: %d", skipped)
    logger.info("Questions exported: %d", len(question_records))
    if total_usage:
        logger.info("Reported total tokens: %d", total_usage)
    logger.info("Output: %s", output_path)
    logger.info("Unprocessed report: %s", unprocessed_report_path)
    _append_log(progress_log_path, f"Unprocessed report: {unprocessed_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
