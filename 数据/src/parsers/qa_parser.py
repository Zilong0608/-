# -*- coding: utf-8 -*-
"""
Q&A解析器
识别并解析文本中的问答对
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from ..utils.logger import get_logger
from ..config.settings import ChunkerConfig


@dataclass
class QAPair:
    """问答对"""
    question: str
    answer: str
    question_num: Optional[int] = None  # 题号
    source_file: Optional[str] = None
    page_num: Optional[int] = None
    start_pos: int = 0  # 在原文中的起始位置
    end_pos: int = 0  # 在原文中的结束位置

    @property
    def full_text(self) -> str:
        """完整的问答文本"""
        return f"{self.question}\n\n{self.answer}"

    @property
    def char_count(self) -> int:
        return len(self.full_text)

    def to_dict(self) -> dict:
        return {
            'question': self.question,
            'answer': self.answer,
            'question_num': self.question_num,
            'source_file': self.source_file,
            'page_num': self.page_num,
            'start_pos': self.start_pos,
            'end_pos': self.end_pos,
        }


class QAParser:
    """Q&A解析器"""

    def __init__(self, config: Optional[ChunkerConfig] = None):
        """
        初始化解析器

        Args:
            config: 分段配置
        """
        self.config = config or ChunkerConfig()
        self.logger = get_logger("qa_parser")

        # 编译正则表达式
        self._compile_patterns()

    def _compile_patterns(self):
        """编译Q&A识别的正则表达式"""
        # 问题模式
        self.question_patterns = [
            # Markdown????: ## 1. ??
            re.compile(r'^#{1,4}\s*(\d+)[\.\u3001\uFF1A:]?\s*(.+)$', re.MULTILINE),
            # Markdown????: ## ???
            re.compile(r'^#{1,6}\s*(.+?[\?\uFF1F])\s*$', re.MULTILINE),

            # ??????: 1. ?? ? 1???
            re.compile(r'^(\d+)[\.\u3001\uFF1A:]\s*(.+?)(?:\?|\uFF1F|$)', re.MULTILINE),

            # Q: ??
            re.compile(r'^[Qq]\s*(\d*)[\.\u3001\uFF1A:]?\s*(.+)$', re.MULTILINE),

            # ????
            re.compile(r'^\u95ee\s*(\d*)[\.\u3001\uFF1A:]?\s*(.+)$', re.MULTILINE),

            # ??????
            re.compile(r'^\u3010[\u95ee\u9898]*(\d*)\u3011\s*(.+)$', re.MULTILINE),

            # ????: **1. ??**
            re.compile(r'^\*\*(\d+)[\.\u3001]\s*(.+?)\*\*', re.MULTILINE),

            # ??????: - ???
            re.compile(r'^\s*[-*]\s*(.+?[\?\uFF1F])\s*$', re.MULTILINE),

            # Heuristic: question-like lines without explicit punctuation.
            re.compile(
                r'^(?=.{2,120}$).*(?:'
                r'\u4ec0\u4e48|\u6709\u4ec0\u4e48|\u6709\u54ea\u4e9b|\u662f\u4ec0\u4e48|'
                r'\u5982\u4f55|\u600e\u4e48|\u600e\u6837|\u4e3a\u4ec0\u4e48|'
                r'\u662f\u5426|\u533a\u522b|\u4f18\u7f3a\u70b9|\u7279\u70b9|'
                r'\u539f\u7406|\u4f5c\u7528|\u6d41\u7a0b|\u6b65\u9aa4|'
                r'\u6982\u5ff5|\u5b9a\u4e49|\u65b9\u6cd5|\u539f\u56e0'
                r')\s*$',
                re.MULTILINE
            ),
        ]

        self.step_marker_pattern = re.compile(
            r'^(?:'
            r'\u7b2c[\u4e00-\u5341\d]+\u6b65'
            r'|\u6b65\u9aa4\s*[\u4e00-\u5341\d]+'
            r'|step\s*\d+'
            r')',
            re.IGNORECASE
        )

        # 答案开始模式
        self.answer_start_patterns = [
            re.compile(r'^[Aa]\s*[\.、:：]\s*', re.MULTILINE),
            re.compile(r'^答\s*[\.、:：]\s*', re.MULTILINE),
            re.compile(r'^【答案?】\s*', re.MULTILINE),
            re.compile(r'^解[答析]\s*[\.、:：]?\s*', re.MULTILINE),
        ]

    def parse(
        self,
        text: str,
        source_file: Optional[str] = None,
        page_num: Optional[int] = None
    ) -> List[QAPair]:
        """
        解析文本中的问答对

        Args:
            text: 输入文本
            source_file: 来源文件名
            page_num: 页码

        Returns:
            问答对列表
        """
        if not text or not text.strip():
            return []

        text = self._normalize_text(text)

        # 尝试多种解析策略
        qa_pairs = []

        # 策略1: 基于明确的问题标记
        qa_pairs = self._parse_by_question_markers(text)

        # 如果没找到，策略2: 基于代码块分隔
        if not qa_pairs:
            qa_pairs = self._parse_by_code_blocks(text)

        # 如果还是没找到，策略3: 基于段落分隔
        if not qa_pairs:
            qa_pairs = self._parse_by_paragraphs(text)

        # 填充元信息
        for qa in qa_pairs:
            qa.source_file = source_file
            qa.page_num = page_num

        self.logger.debug(f"解析出 {len(qa_pairs)} 个问答对")
        return qa_pairs

    def _normalize_text(self, text: str) -> str:
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _parse_by_question_markers(self, text: str) -> List[QAPair]:
        """基于问题标记解析"""
        # 找出所有问题的位置
        question_positions = []

        for pattern in self.question_patterns:
            for match in pattern.finditer(text):
                # 提取题号和问题内容
                groups = match.groups()
                if len(groups) >= 2:
                    num_str, question_text = groups[0], groups[1]
                else:
                    num_str, question_text = '', groups[0] if groups else ''

                question_num = int(num_str) if num_str and num_str.isdigit() else None
                if self.step_marker_pattern.match(question_text):
                    continue

                question_positions.append({
                    'start': match.start(),
                    'end': match.end(),
                    'num': question_num,
                    'question': match.group(0).strip(),
                    'question_text': question_text.strip(),
                })

        if not question_positions:
            return []

        # 按位置排序
        question_positions.sort(key=lambda x: x['start'])

        # 去重（同一位置可能被多个模式匹配）
        unique_positions = []
        last_end = -1
        for pos in question_positions:
            if pos['start'] >= last_end:
                unique_positions.append(pos)
                last_end = pos['end']

        # 提取问答对
        qa_pairs = []
        for i, pos in enumerate(unique_positions):
            # 确定答案的范围：从问题结束到下一个问题开始（或文本结束）
            answer_start = pos['end']
            if i + 1 < len(unique_positions):
                answer_end = unique_positions[i + 1]['start']
            else:
                answer_end = len(text)

            answer_text = text[answer_start:answer_end].strip()

            # 清理答案文本（移除答案标记）
            answer_text = self._clean_answer_text(answer_text)

            if answer_text:  # 只保留有答案的问题
                qa_pairs.append(QAPair(
                    question=pos['question'],
                    answer=answer_text,
                    question_num=pos['num'],
                    start_pos=pos['start'],
                    end_pos=answer_end,
                ))

        return qa_pairs

    def _parse_by_code_blocks(self, text: str) -> List[QAPair]:
        """基于代码块分隔解析（适用于网安面试题那种格式）"""
        # 匹配 ## 标题 + ```代码块``` 的模式
        pattern = re.compile(
            r'^(#{1,4}\s*\d*[\.、,，]?\s*.+?)$\s*```[\w]*\s*(.+?)```',
            re.MULTILINE | re.DOTALL
        )

        qa_pairs = []
        for match in pattern.finditer(text):
            question = match.group(1).strip()
            answer = match.group(2).strip()

            # 提取题号
            num_match = re.search(r'(\d+)', question)
            question_num = int(num_match.group(1)) if num_match else None

            qa_pairs.append(QAPair(
                question=question,
                answer=answer,
                question_num=question_num,
                start_pos=match.start(),
                end_pos=match.end(),
            ))

        return qa_pairs

    def _parse_by_paragraphs(self, text: str) -> List[QAPair]:
        """基于段落分隔解析（最后的备选方案）"""
        # 按双换行分割
        paragraphs = re.split(r'\n\s*\n', text)

        qa_pairs = []
        current_question = None
        current_answer_parts = []
        current_start = 0
        position = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                position += 2  # 空段落的长度
                continue

            # 判断是否是问题（以?/?结尾，或者以数字开头）
            is_question = (
                para.endswith('?') or
                para.endswith('？') or
                re.match(r'^\d+[\.、]', para) or
                re.match(r'^#{1,4}\s*\d+', para)
            )

            if is_question:
                # 保存之前的问答对
                if current_question and current_answer_parts:
                    qa_pairs.append(QAPair(
                        question=current_question,
                        answer='\n\n'.join(current_answer_parts),
                        start_pos=current_start,
                        end_pos=position,
                    ))

                current_question = para
                current_answer_parts = []
                current_start = position
            else:
                if current_question:
                    current_answer_parts.append(para)

            position += len(para) + 2

        # 保存最后一个问答对
        if current_question and current_answer_parts:
            qa_pairs.append(QAPair(
                question=current_question,
                answer='\n\n'.join(current_answer_parts),
                start_pos=current_start,
                end_pos=position,
            ))

        return qa_pairs


    def parse_headings(
        self,
        text: str,
        source_file: Optional[str] = None,
        page_num: Optional[int] = None
    ) -> List[QAPair]:
        # Parse Markdown headings as question boundaries.
        if not text or not text.strip():
            return []

        text = self._normalize_text(text)
        heading_pattern = re.compile(r'^#{1,6}\s*(.+)$', re.MULTILINE)
        positions = []
        for match in heading_pattern.finditer(text):
            question_text = match.group(1).strip()
            if self.step_marker_pattern.match(question_text):
                continue
            positions.append({
                'start': match.start(),
                'end': match.end(),
                'question': match.group(0).strip(),
                'question_text': question_text,
            })

        if not positions:
            return []

        qa_pairs = []
        for i, pos in enumerate(positions):
            answer_start = pos['end']
            answer_end = positions[i + 1]['start'] if i + 1 < len(positions) else len(text)
            answer_text = text[answer_start:answer_end].strip()
            answer_text = self._clean_answer_text(answer_text)
            if not answer_text:
                continue

            qa = QAPair(
                question=pos['question'],
                answer=answer_text,
                start_pos=pos['start'],
                end_pos=answer_end,
            )
            qa.source_file = source_file
            qa.page_num = page_num
            qa_pairs.append(qa)

        return qa_pairs

    def _clean_answer_text(self, text: str) -> str:
        """清理答案文本"""
        # 移除答案开始标记
        for pattern in self.answer_start_patterns:
            text = pattern.sub('', text)

        # 移除开头的空行
        text = text.lstrip('\n')

        return text.strip()

    def merge_short_qas(
        self,
        qa_pairs: List[QAPair],
        min_length: int = 50
    ) -> List[QAPair]:
        """
        合并过短的问答对

        Args:
            qa_pairs: 问答对列表
            min_length: 最小长度

        Returns:
            合并后的问答对列表
        """
        if not qa_pairs:
            return []

        merged = []
        current = None

        for qa in qa_pairs:
            if current is None:
                current = qa
            elif current.char_count < min_length:
                # 合并到下一个
                current = QAPair(
                    question=current.question,
                    answer=f"{current.answer}\n\n{qa.question}\n{qa.answer}",
                    question_num=current.question_num,
                    source_file=current.source_file,
                    page_num=current.page_num,
                    start_pos=current.start_pos,
                    end_pos=qa.end_pos,
                )
            else:
                merged.append(current)
                current = qa

        if current:
            merged.append(current)

        return merged
