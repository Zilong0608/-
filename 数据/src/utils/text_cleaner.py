# -*- coding: utf-8 -*-
"""
Text cleanup and resume-template detection helpers for RAG ingestion.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Optional


PAGE_NUMBER_PATTERNS = [
    re.compile(r'^\s*第?\s*\d+\s*页\s*$', re.IGNORECASE),
    re.compile(r'^\s*\d+\s*/\s*\d+\s*$'),
    re.compile(r'^\s*page\s*\d+\s*$', re.IGNORECASE),
]

RESUME_PATH_KEYWORDS = [
    '简历', '简历模板', '模板', 'resume', 'cv', '求职', '应聘', '求职信', '自荐信'
]

RESUME_SECTION_KEYWORDS = [
    '个人信息', '基本信息', '联系方式', '邮箱', '电话', '求职意向', '期望薪资',
    '教育经历', '工作经历', '项目经历', '实习经历', '技能', '技能特长', '荣誉',
    '证书', '自我评价', '个人简介', '个人优势', '校园经历'
]

HEADING_PATTERNS = [
    re.compile(r'^\s*#{1,6}\s+.+$'),
    re.compile(r'^\s*\d+\s*[\.、]\s*.+$'),
    re.compile(r'^\s*[一二三四五六七八九十]+\s*[、\.]\s*.+$'),
]

LIST_PATTERNS = [
    re.compile(r'^\s*[-\*•]\s+.+$'),
    re.compile(r'^\s*\d+\s*[\.\)]\s+.+$'),
]


DROP_LINE_KEYWORDS = [
    '\u4ee3\u7801\u968f\u60f3\u5f55',
    '\u77e5\u8bc6\u661f\u7403',
    '\u5c0f\u6797coding',
    '\u725b\u5ba2\u7f51',
    '\u535a\u5ba2\u8d44\u6599',
]

def _normalize_line(line: str) -> str:
    line = line.strip().lower()
    line = re.sub(r'\s+', ' ', line)
    return line


def _is_noise_line(line: str) -> bool:
    if not line:
        return True
    if any(pat.match(line) for pat in PAGE_NUMBER_PATTERNS):
        return True
    if len(line) <= 2:
        return True
    word_chars = re.findall(r'[\w\u4e00-\u9fff]', line)
    return len(word_chars) / max(len(line), 1) < 0.2


def _should_drop_line(line: str) -> bool:
    for keyword in DROP_LINE_KEYWORDS:
        if keyword and keyword in line:
            return True
    return False


def clean_extracted_text(text: str) -> str:
    """
    Normalize whitespace and drop obvious headers/footers/noise lines.
    """
    if not text:
        return ""

    raw_lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    lines = [line.strip() for line in raw_lines]

    lines = [line for line in lines if line and not _should_drop_line(line)]
    lines = [line for line in lines if not _is_noise_line(line)]

    normalized = [_normalize_line(line) for line in lines]
    counts = Counter(normalized)
    filtered = []
    for line, norm in zip(lines, normalized):
        if counts[norm] >= 3 and len(line) <= 40:
            continue
        filtered.append(line)

    cleaned = '\n'.join(filtered)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def is_resume_template(path: Optional[Path], text: str) -> bool:
    """
    Heuristic resume/template detector based on path and section keywords.
    """
    path_str = str(path).lower() if path else ""
    if any(keyword.lower() in path_str for keyword in RESUME_PATH_KEYWORDS):
        return True

    if not text:
        return False

    hits = 0
    for keyword in RESUME_SECTION_KEYWORDS:
        if keyword in text:
            hits += 1

    if hits >= 4 and len(text) < 4000:
        return True
    if hits >= 6:
        return True

    return False


def text_to_markdown(text: str) -> str:
    """
    Convert cleaned text into lightweight Markdown.
    """
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines()]
    md_lines = []
    for line in lines:
        if not line:
            md_lines.append("")
            continue

        if any(pat.match(line) for pat in HEADING_PATTERNS):
            # Normalize to heading
            content = re.sub(r'^\s*[#\d一二三四五六七八九十\.\、\)]*\s*', '', line)
            if content:
                md_lines.append(f"## {content}")
            else:
                md_lines.append(line)
            continue

        if any(pat.match(line) for pat in LIST_PATTERNS):
            content = re.sub(r'^\s*[-\*•\d\.\)]+\s*', '', line)
            md_lines.append(f"- {content}" if content else line)
            continue

        md_lines.append(line)

    md_text = "\n".join(md_lines)
    md_text = re.sub(r'\n{3,}', '\n\n', md_text)
    return md_text.strip()
