# -*- coding: utf-8 -*-
"""
Merge, clean, and deduplicate questions in "第一轮仔细清洗" using LLM.
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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils.logger import setup_logger


SYSTEM_PROMPT = (
    "你是严格的技术面试教官，负责审查候选问题是否可独立作为面试题。"
    "只保留可以直接问候选人的问题；合并明显断裂的碎片；删除目录、页码、"
    "参考资料、无上下文的残句或无意义的短语。"
    "不要扩写或编造内容。"
    "只返回 JSON 对象，键为 questions，值为字符串数组。"
)

USER_PROMPT_TEMPLATE = (
    "候选问题列表可能含噪音、断句、重复或残缺。请清洗并输出 JSON。\n"
    "规则：\n"
    "1) 仅保留可独立作为面试问题的句子。\n"
    "2) 若某行明显是上一行的续写，请合并成一个完整问题。\n"
    "3) 删除目录/页码/参考资料/不完整短语。\n"
    "4) 不要扩写或引入新信息。\n"
    "5) 仅输出 JSON 对象，格式为 {{\"questions\": [...]}}。\n\n"
    "候选列表:\n{items_json}\n"
)


PUNCT_CLEAN_RE = re.compile(r"[\u3000\s]+")
LEADING_NUM_RE = re.compile(r"^[\s\(\[【{]*([0-9]{1,3}|[一二三四五六七八九十]+)[\.\、\)\]】}：:\-]*\s*")
DOT_LEADER_RE = re.compile(r"[\.·]{3,}\s*\d+\s*[?？]?$")
TRAILING_PAGE_RE = re.compile(r"\s+\d+\s*[?？]?$")
NOISE_RE = re.compile(
    r"^(?:"
    r"参考资料|参考文献|资料来源|目录|前言|版权|致谢|附录|"
    r"chapter|section|page|图|表|目录|contents"
    r")",
    re.IGNORECASE
)


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
    response_format: str,
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
    if response_format == "object":
        payload["response_format"] = {"type": "json_object"}
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
        raw = raw.strip("`")
    if raw.startswith("{") and raw.endswith("}"):
        data = json.loads(raw)
        if isinstance(data, dict) and "questions" in data:
            return data["questions"]
        if isinstance(data, dict) and "items" in data:
            return data["items"]
    if raw.startswith("[") and raw.endswith("]"):
        return json.loads(raw)
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError("No JSON array found in model output")


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u3000", " ").strip()
    text = PUNCT_CLEAN_RE.sub(" ", text)
    text = LEADING_NUM_RE.sub("", text).strip()
    text = DOT_LEADER_RE.sub("", text).strip()
    text = TRAILING_PAGE_RE.sub("", text).strip()
    return text


def _is_noise(text: str) -> bool:
    if not text:
        return True
    if len(_strip_non_text(text)) < 4:
        return True
    if NOISE_RE.search(text):
        return True
    return False


def _strip_non_text(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", text)


def _dedup_key(text: str) -> str:
    if not text:
        return ""
    key = text.lower().strip()
    key = re.sub(r"[\s\(\)\[\]{}<>《》“”\"'`~·•\-–—_]+", "", key)
    key = re.sub(r"[。，、；：！？!?.,;:]+", "", key)
    key = LEADING_NUM_RE.sub("", key)
    return key


def _as_question_text(item: Any) -> Optional[str]:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("question", "text", "q", "content"):
            if key in item and isinstance(item[key], str):
                return item[key]
    return None


def _iter_question_lists(data: Any) -> Iterable[Tuple[Optional[str], List[Any]]]:
    if isinstance(data, list):
        yield None, data
        return
    if not isinstance(data, dict):
        return
    if "questions" in data and isinstance(data["questions"], list):
        yield None, data["questions"]
    categories = data.get("categories")
    if isinstance(categories, list):
        for cat in categories:
            cat_name = cat.get("category") if isinstance(cat, dict) else None
            subs = cat.get("subcategories", []) if isinstance(cat, dict) else []
            if subs:
                for sub in subs:
                    sub_name = sub.get("subcategory") if isinstance(sub, dict) else None
                    questions = sub.get("questions", []) if isinstance(sub, dict) else []
                    if questions:
                        hint = "/".join([n for n in [cat_name, sub_name] if n])
                        yield hint or cat_name or sub_name, questions
            questions = cat.get("questions", []) if isinstance(cat, dict) else []
            if questions:
                yield cat_name, questions
    if isinstance(categories, dict):
        for cat_name, cat_obj in categories.items():
            if isinstance(cat_obj, dict) and "questions" in cat_obj:
                yield cat_name, cat_obj["questions"]
            elif isinstance(cat_obj, list):
                yield cat_name, cat_obj
    for key, value in data.items():
        if isinstance(value, dict) and "questions" in value and isinstance(value["questions"], list):
            yield key, value["questions"]


def _batch_items(items: List[str], max_chars: int, max_items: int) -> List[List[str]]:
    batches: List[List[str]] = []
    current: List[str] = []
    current_len = 0
    for item in items:
        add_len = len(item) + 2
        if current and (current_len + add_len > max_chars or len(current) >= max_items):
            batches.append(current)
            current = [item]
            current_len = len(item)
        else:
            current.append(item)
            current_len += add_len
    if current:
        batches.append(current)
    return batches


def _group_by_hint(items: List[Tuple[str, Optional[str]]]) -> Dict[Optional[str], List[str]]:
    grouped: Dict[Optional[str], List[str]] = {}
    for text, hint in items:
        grouped.setdefault(hint, []).append(text)
    return grouped


def _infer_category(file_name: str, hint: Optional[str]) -> str:
    name = f"{file_name} {hint or ''}".lower()
    if "网安" in name or "网络安全" in name or "安全" in name:
        return "网安"
    if "llm" in name or "大模型" in name:
        return "LLM"
    if "oracle" in name:
        return "Oracle"
    if "数据库" in name or "sql" in name:
        return "数据库"
    if "数据分析" in name:
        return "数据分析"
    if "深度学习" in name or "dl" in name:
        return "深度学习"
    if "机器学习" in name or "ml" in name:
        return "机器学习"
    if "slam" in name:
        return "SLAM"
    if "web3" in name:
        return "Web3"
    if "测试" in name or "jenkins" in name:
        return "测试"
    if "图形算法" in name or "算法" in name:
        return "算法"
    if "综合" in name or "通用" in name:
        return "综合"
    return "其他"


def _collect_questions_from_file(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records: List[Dict[str, Any]] = []
    for hint, questions in _iter_question_lists(data):
        for item in questions:
            text = _as_question_text(item)
            if not text:
                continue
            records.append({
                "text": text,
                "hint": hint,
            })
    return records


def main() -> int:
    config = get_config()
    parser = argparse.ArgumentParser(description="Merge and deduplicate questions with LLM")
    parser.add_argument("--input-dir", default=str(Path(config.paths.root_dir) / "第一轮仔细清洗"))
    parser.add_argument("--output", default=str(Path(config.paths.root_dir) / "第一轮仔细清洗" / "CLEAN_ALL_DEDUP_LLM.json"))
    parser.add_argument("--report", default=str(Path(config.paths.data_reports) / "dedup_questions_report.json"))
    parser.add_argument("--model", default="gpt-5-nano-2025-08-07")
    parser.add_argument("--max-output-tokens", type=int, default=800)
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--max-items", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--response-format", choices=["object", "array"], default="object")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("Missing OPENAI_API_KEY")
        return 1

    logger = setup_logger(
        name="merge_dedup_questions_llm",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)
    report_path = Path(args.report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob("*.json"))
    if not json_files:
        logger.error(f"No JSON files found in {input_dir}")
        return 1

    logger.info("=" * 60)
    logger.info("Merge & Dedup Questions (LLM)")
    logger.info("=" * 60)
    logger.info(f"Input dir: {input_dir}")
    logger.info(f"Files: {len(json_files)}")
    logger.info(f"Model: {args.model}")

    raw_questions = 0
    removed_noise = 0
    llm_cleaned = 0
    total_batches = 0
    duplicates: Dict[str, Dict[str, Any]] = {}
    category_map: Dict[str, List[str]] = {}
    seen_keys: Dict[str, str] = {}

    for file_path in json_files:
        records = _collect_questions_from_file(file_path)
        if not records:
            logger.warning(f"No questions found in {file_path.name}")
            continue
        raw_questions += len(records)

        cleaned_candidates: List[Tuple[str, Optional[str]]] = []
        for rec in records:
            text = _normalize_text(rec["text"])
            if _is_noise(text):
                removed_noise += 1
                continue
            cleaned_candidates.append((text, rec.get("hint")))

        if not cleaned_candidates:
            logger.warning(f"All questions filtered in {file_path.name}")
            continue

        grouped = _group_by_hint(cleaned_candidates)
        total_file_batches = 0
        for hint, items in grouped.items():
            total_file_batches += len(_batch_items(items, args.max_chars, args.max_items))
        total_batches += total_file_batches

        logger.info(f"{file_path.name}: {len(cleaned_candidates)} candidates, {total_file_batches} batches")
        if args.dry_run:
            continue

        for hint, items in grouped.items():
            batches = _batch_items(items, args.max_chars, args.max_items)
            for batch_index, batch in enumerate(batches, 1):
                user_prompt = USER_PROMPT_TEMPLATE.format(items_json=json.dumps(batch, ensure_ascii=False))
                try:
                    response = _call_openai(
                        api_key=api_key,
                        model=args.model,
                        system_prompt=SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        max_output_tokens=args.max_output_tokens,
                        timeout=args.timeout,
                        base_url=args.base_url,
                        max_retries=args.retries,
                        retry_sleep=args.retry_sleep,
                        response_format=args.response_format,
                    )
                    content = response["choices"][0]["message"]["content"]
                    items = _extract_json_array(content)
                    cleaned = []
                    for item in items:
                        text = _as_question_text(item)
                        if not text:
                            continue
                        text = _normalize_text(text)
                        if _is_noise(text):
                            continue
                        cleaned.append(text)
                    llm_cleaned += len(cleaned)

                    for text in cleaned:
                        category = _infer_category(file_path.name, hint)
                        key = _dedup_key(text)
                        if not key:
                            continue
                        if key in seen_keys:
                            dup = duplicates.setdefault(key, {
                                "question": seen_keys[key],
                                "sources": set()
                            })
                            dup["sources"].add(file_path.name)
                            continue
                        seen_keys[key] = text
                        category_map.setdefault(category, []).append(text)

                    logger.info(f"{file_path.name} [{hint or 'default'}] batch {batch_index}/{len(batches)} done, kept {len(cleaned)}")
                except Exception as e:
                    snippet = ""
                    try:
                        if "content" in locals():
                            snippet = str(content).strip().replace("\n", " ")[:200]
                    except Exception:
                        snippet = ""
                    detail = f"{e}"
                    if snippet:
                        detail = f"{detail} | output: {snippet}"
                    logger.error(f"LLM failed on {file_path.name} [{hint or 'default'}] batch {batch_index}: {detail}")
                    continue

    if args.dry_run:
        logger.info("Dry run completed")
        return 0

    for dup in duplicates.values():
        if isinstance(dup["sources"], set):
            dup["sources"] = sorted(dup["sources"])

    categories_output = {}
    total_unique = 0
    for cat, questions in sorted(category_map.items()):
        deduped = []
        seen_local = set()
        for q in questions:
            k = _dedup_key(q)
            if k in seen_local:
                continue
            seen_local.add(k)
            deduped.append(q)
        categories_output[cat] = {
            "count": len(deduped),
            "questions": deduped
        }
        total_unique += len(deduped)

    output = {
        "version": "llm_dedup_v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_questions": total_unique,
        "categories": categories_output
    }

    report = {
        "input_dir": str(input_dir),
        "input_files": [p.name for p in json_files],
        "raw_questions": raw_questions,
        "removed_noise": removed_noise,
        "llm_cleaned": llm_cleaned,
        "unique_questions": total_unique,
        "total_batches": total_batches,
        "duplicates": list(duplicates.values()),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("Completed")
    logger.info(f"Output: {output_path}")
    logger.info(f"Report: {report_path}")
    logger.info(f"Unique: {total_unique}")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
