# -*- coding: utf-8 -*-
"""
Step 3 (LLM): parse Q&A for a single file and write chunks.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.parsers import Chunker, QAPair


SYSTEM_PROMPT = (
    "You are a strict Q&A extractor for interview prep documents. "
    "Return ONLY a JSON array of objects with keys: question, answer. "
    "Do not add commentary or markdown. "
    "Keep multi-step answers together; do not split numbered steps into separate Q&As. "
    "Do NOT treat step headings like '第X步/步骤X/Step X' as questions. "
    "Only extract questions that are explicitly present or strongly implied by headings. "
    "If a question has no answer, omit it."
)

STEP_HEADING_PATTERN = re.compile(
    r'^(?:'
    r'\u7b2c[\u4e00-\u5341\d]+\u6b65'
    r'|\u6b65\u9aa4\s*[\u4e00-\u5341\d]+'
    r'|step\s*\d+'
    r')',
    re.IGNORECASE
)


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
    sections: List[tuple[Optional[str], str]] = []
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
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
    }
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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[\w-]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "qas" in parsed:
            parsed = parsed["qas"]
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


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 1.5))


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Q&A parser for a single file")
    parser.add_argument("--source-match", required=True, help="substring in source_path or file_name")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-chars", type=int, default=3000)
    parser.add_argument("--max-sections", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=800)
    parser.add_argument("--min-answer-len", type=int, default=0)
    parser.add_argument("--max-chunk-size", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--use-markdown", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--raw-output-dir", default="")
    args = parser.parse_args()

    config = get_config()
    logger = setup_logger(
        name="parse_qa_llm",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not set.")
        return 1

    input_path = config.paths.data_ingest / "extracted_documents.json"
    if not input_path.exists():
        logger.error("Please run 02_extract_text.py first.")
        return 1

    with open(input_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    match = args.source_match.lower()
    candidates = [
        d for d in docs
        if match in (d.get("source_path") or "").lower()
        or match in (d.get("file_name") or "").lower()
    ]
    if not candidates:
        logger.error("No document matched the source-match filter.")
        return 1
    if len(candidates) > 1:
        logger.error("Multiple documents matched source-match; be more specific.")
        for d in candidates[:5]:
            logger.error("  %s", d.get("source_path") or d.get("file_name"))
        return 1

    doc = candidates[0]
    if args.use_markdown:
        content_text = doc.get("markdown_text") or doc.get("full_text") or ""
    else:
        content_text = doc.get("full_text") or doc.get("markdown_text") or ""
    if not content_text.strip():
        logger.error("Document has no text content.")
        return 1

    logger.info("Using %s text for LLM extraction", "markdown" if args.use_markdown else "full_text")

    sections = split_markdown_sections(content_text, args.max_chars)
    if args.max_sections and args.max_sections > 0:
        sections = sections[:args.max_sections]

    if not sections:
        logger.error("No sections generated from text.")
        return 1

    est_tokens = sum(_estimate_tokens(s) for s in sections)
    logger.info("Sections: %d", len(sections))
    logger.info("Estimated input tokens: ~%d", est_tokens)
    if args.dry_run:
        return 0

    min_answer_len = args.min_answer_len or config.quality.min_content_length
    chunker = Chunker(config.chunker)
    if args.max_chunk_size and args.max_chunk_size > 0:
        chunker.config.max_chunk_size = args.max_chunk_size

    all_qas: List[QAPair] = []
    raw_chunks: List[Dict[str, Any]] = []
    total_usage = 0
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    for idx, section in enumerate(sections, start=1):
        user_prompt = (
            "Extract Q&A pairs from the text below. "
            "Return JSON array with objects: {\"question\": \"...\", \"answer\": \"...\"}.\n\n"
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
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            logger.error("HTTP error on section %d: %s", idx, body)
            return 1
        except Exception as exc:
            logger.error("Request failed on section %d: %s", idx, exc)
            return 1

        usage = resp.get("usage", {})
        total_usage += int(usage.get("total_tokens") or 0)

        content = ""
        try:
            content = resp["choices"][0]["message"]["content"]
        except Exception:
            logger.error("No content in response for section %d", idx)
            continue

        items = _extract_json_array(content)
        if not items:
            logger.warning("No Q&A parsed from section %d", idx)
            raw_chunks.append({
                "chunk_id": f"raw_{idx:06d}",
                "content": section,
                "chunk_type": "raw",
                "source_file": doc.get("source_path"),
                "section_index": idx,
                "char_count": len(section),
                "metadata": {
                    "llm": True,
                    "source_match": args.source_match,
                    "reason": "no_qa",
                },
            })
            continue

        added = 0
        for item in items:
            question = (item.get("question") or "").strip()
            answer = (item.get("answer") or "").strip()
            if not question or not answer:
                continue
            if len(answer) < min_answer_len:
                continue
            all_qas.append(QAPair(
                question=question,
                answer=answer,
                source_file=doc.get("source_path"),
                page_num=None,
                start_pos=0,
                end_pos=0,
            ))
            added += 1

        if added == 0:
            raw_chunks.append({
                "chunk_id": f"raw_{idx:06d}",
                "content": section,
                "chunk_type": "raw",
                "source_file": doc.get("source_path"),
                "section_index": idx,
                "char_count": len(section),
                "metadata": {
                    "llm": True,
                    "source_match": args.source_match,
                    "reason": "filtered_out",
                },
            })

        if args.sleep:
            time.sleep(args.sleep)

        logger.info("Section %d/%d done. QAs so far: %d", idx, len(sections), len(all_qas))

    if not all_qas:
        logger.error("No Q&A pairs extracted.")
        return 1

    chunks = chunker.chunk_qa_pairs(all_qas, source_file=doc.get("source_path"))
    for chunk in chunks:
        chunk.metadata["category"] = doc.get("category", "")
        chunk.metadata["llm"] = True
        chunk.metadata["source_match"] = args.source_match

    output_dir = config.paths.data_chunks
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (output_dir / "chunks_llm.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in chunks], f, ensure_ascii=False, indent=2)

    if raw_chunks:
        raw_dir = Path(args.raw_output_dir) if args.raw_output_dir else (output_dir / "llm_raw")
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / "raw_chunks.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw_chunks, f, ensure_ascii=False, indent=2)
        logger.info("Raw chunks saved: %d", len(raw_chunks))
        logger.info("Raw output: %s", raw_path)

    logger.info("LLM Q&A pairs: %d", len(all_qas))
    logger.info("Chunks saved: %d", len(chunks))
    if total_usage:
        logger.info("Reported total tokens: %d", total_usage)
    logger.info("Output: %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
