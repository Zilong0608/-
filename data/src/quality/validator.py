# -*- coding: utf-8 -*-
"""
质量校验器
检测乱码、空内容、格式异常等问题
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import json
import random

from ..utils.logger import get_logger
from ..config.settings import QualityConfig
from ..parsers.chunker import Chunk


@dataclass
class ValidationResult:
    """校验结果"""
    chunk_id: str
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'chunk_id': self.chunk_id,
            'is_valid': self.is_valid,
            'issues': self.issues,
            'scores': self.scores,
        }


class QualityValidator:
    """质量校验器"""

    def __init__(self, config: Optional[QualityConfig] = None):
        """
        初始化校验器

        Args:
            config: 质量配置
        """
        self.config = config or QualityConfig()
        self.logger = get_logger("quality_validator")

    def validate_chunk(self, chunk: Chunk) -> ValidationResult:
        """
        校验单个chunk

        Args:
            chunk: 输入chunk

        Returns:
            校验结果
        """
        issues = []
        scores = {}

        content = chunk.content

        # 1. 检查空内容
        if not content or not content.strip():
            issues.append("内容为空")
            return ValidationResult(
                chunk_id=chunk.chunk_id,
                is_valid=False,
                issues=issues,
                scores={'overall': 0.0}
            )

        # 2. 检查内容长度
        if len(content) < self.config.min_content_length:
            issues.append(f"内容过短（{len(content)}字符）")

        # 3. 检查乱码
        garbled_ratio = self._check_garbled(content)
        scores['garbled_ratio'] = garbled_ratio
        if garbled_ratio > self.config.garbled_threshold:
            issues.append(f"疑似乱码（非正常字符占比: {garbled_ratio:.2%}）")

        # 4. 检查重复内容
        repetition_ratio = self._check_repetition(content)
        scores['repetition_ratio'] = repetition_ratio
        if repetition_ratio > 0.5:
            issues.append(f"大量重复内容（重复率: {repetition_ratio:.2%}）")

        # 5. 检查特殊字符
        special_char_ratio = self._check_special_chars(content)
        scores['special_char_ratio'] = special_char_ratio
        if special_char_ratio > 0.3:
            issues.append(f"特殊字符过多（占比: {special_char_ratio:.2%}）")

        # 6. 检查Q&A完整性（如果是Q&A类型）
        if chunk.chunk_type == 'qa':
            qa_issues = self._check_qa_completeness(chunk)
            issues.extend(qa_issues)

        # 计算综合分数
        overall_score = self._calculate_overall_score(scores, issues)
        scores['overall'] = overall_score

        is_valid = len(issues) == 0 or overall_score >= 0.6

        return ValidationResult(
            chunk_id=chunk.chunk_id,
            is_valid=is_valid,
            issues=issues,
            scores=scores,
        )

    def validate_chunks(
        self,
        chunks: List[Chunk],
        remove_invalid: bool = False
    ) -> Tuple[List[Chunk], List[ValidationResult]]:
        """
        批量校验chunks

        Args:
            chunks: chunk列表
            remove_invalid: 是否移除无效的chunk

        Returns:
            (处理后的chunks, 校验结果列表)
        """
        results = []
        valid_chunks = []

        for chunk in chunks:
            result = self.validate_chunk(chunk)
            results.append(result)

            if result.is_valid or not remove_invalid:
                if result.is_valid:
                    valid_chunks.append(chunk)
            else:
                self.logger.warning(
                    f"移除无效chunk {chunk.chunk_id}: {result.issues}"
                )

        # 统计
        valid_count = sum(1 for r in results if r.is_valid)
        self.logger.info(
            f"校验完成: {valid_count}/{len(chunks)} 有效 "
            f"({valid_count/len(chunks)*100:.1f}%)"
        )

        if remove_invalid:
            return valid_chunks, results
        return chunks, results

    def _check_garbled(self, text: str) -> float:
        """
        检查乱码比例

        Args:
            text: 输入文本

        Returns:
            乱码字符占比
        """
        if not text:
            return 0.0

        # 正常字符：中文、英文、数字、常用标点
        normal_pattern = re.compile(
            r'[\u4e00-\u9fff'  # 中文
            r'a-zA-Z'  # 英文
            r'0-9'  # 数字
            r'\s'  # 空白
            r'，。！？、；：""''（）【】《》'  # 中文标点
            r',.!?;:\'\"()\[\]{}<>'  # 英文标点
            r'\-\+\*\/\=\#\@\%\&\_\~\`'  # 特殊符号
            r'\n\r\t'  # 换行制表
            r']'
        )

        normal_chars = len(normal_pattern.findall(text))
        total_chars = len(text)

        if total_chars == 0:
            return 0.0

        abnormal_ratio = 1 - (normal_chars / total_chars)
        return abnormal_ratio

    def _check_repetition(self, text: str) -> float:
        """
        检查重复内容比例

        Args:
            text: 输入文本

        Returns:
            重复内容占比
        """
        if not text or len(text) < 20:
            return 0.0

        # 检查连续重复的模式
        # 例如："aaaa" 或 "abcabcabc"
        total_len = len(text)
        repeated_len = 0

        # 检查单字符重复
        single_repeat = re.findall(r'(.)\1{4,}', text)
        for match in single_repeat:
            repeated_len += len(match) * 4

        # 检查短语重复
        for length in [3, 5, 10]:
            for i in range(len(text) - length * 2):
                pattern = text[i:i+length]
                if pattern * 2 in text[i:]:
                    count = text[i:].count(pattern)
                    if count > 2:
                        repeated_len += len(pattern) * (count - 1)
                        break

        return min(repeated_len / total_len, 1.0)

    def _check_special_chars(self, text: str) -> float:
        """
        检查特殊字符比例

        Args:
            text: 输入文本

        Returns:
            特殊字符占比
        """
        if not text:
            return 0.0

        # 特殊字符（不常见的符号）
        special_chars = re.findall(
            r'[^\u4e00-\u9fffa-zA-Z0-9\s，。！？、；：""''（）【】《》,.!?;:\'\"()\[\]{}<>\-\+\*\/\=\#\@\%\&\_\~\`\n\r\t]',
            text
        )

        return len(special_chars) / len(text) if text else 0.0

    def _check_qa_completeness(self, chunk: Chunk) -> List[str]:
        """
        检查Q&A完整性

        Args:
            chunk: Q&A类型的chunk

        Returns:
            问题列表
        """
        issues = []

        if not chunk.question:
            issues.append("缺少问题")
        elif len(chunk.question) < 5:
            issues.append("问题过短")

        if not chunk.answer:
            issues.append("缺少答案")
        elif len(chunk.answer) < 10:
            issues.append("答案过短")

        return issues

    def _calculate_overall_score(
        self,
        scores: Dict[str, float],
        issues: List[str]
    ) -> float:
        """计算综合分数"""
        # 基础分
        base_score = 1.0

        # 根据各项指标扣分
        if 'garbled_ratio' in scores:
            base_score -= scores['garbled_ratio'] * 0.5

        if 'repetition_ratio' in scores:
            base_score -= scores['repetition_ratio'] * 0.3

        if 'special_char_ratio' in scores:
            base_score -= scores['special_char_ratio'] * 0.2

        # 根据问题数量扣分
        base_score -= len(issues) * 0.1

        return max(0.0, min(1.0, base_score))

    def sample_for_review(
        self,
        chunks: List[Chunk],
        sample_ratio: Optional[float] = None,
        output_path: Optional[Path] = None
    ) -> List[Chunk]:
        """
        抽样用于人工检查

        Args:
            chunks: chunk列表
            sample_ratio: 抽样比例
            output_path: 输出路径

        Returns:
            抽样的chunks
        """
        ratio = sample_ratio or self.config.sample_ratio
        sample_size = max(1, int(len(chunks) * ratio))

        sampled = random.sample(chunks, min(sample_size, len(chunks)))

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                for chunk in sampled:
                    f.write(f"=== {chunk.chunk_id} ===\n")
                    f.write(f"来源: {chunk.source_file}\n")
                    f.write(f"类型: {chunk.chunk_type}\n")
                    f.write(f"问题: {chunk.question}\n")
                    f.write(f"答案: {chunk.answer}\n")
                    f.write(f"Metadata: {chunk.metadata}\n")
                    f.write("\n" + "="*50 + "\n\n")

            self.logger.info(f"抽样结果已保存到: {output_path}")

        return sampled

    def generate_report(
        self,
        results: List[ValidationResult],
        output_path: Path
    ):
        """
        生成质量报告

        Args:
            results: 校验结果列表
            output_path: 输出路径
        """
        report = {
            'total': len(results),
            'valid': sum(1 for r in results if r.is_valid),
            'invalid': sum(1 for r in results if not r.is_valid),
            'issue_summary': {},
            'score_summary': {
                'overall': [],
                'garbled_ratio': [],
                'repetition_ratio': [],
                'special_char_ratio': [],
            },
            'invalid_samples': [],
        }

        # 统计问题类型
        for result in results:
            for issue in result.issues:
                # 提取问题类型（去掉具体数值）
                issue_type = re.sub(r'\d+\.?\d*%?', 'X', issue)
                report['issue_summary'][issue_type] = \
                    report['issue_summary'].get(issue_type, 0) + 1

            # 收集分数
            for key, value in result.scores.items():
                if key in report['score_summary']:
                    report['score_summary'][key].append(value)

            # 收集无效样本
            if not result.is_valid:
                report['invalid_samples'].append(result.to_dict())

        # 计算分数统计
        for key in report['score_summary']:
            scores = report['score_summary'][key]
            if scores:
                report['score_summary'][key] = {
                    'mean': sum(scores) / len(scores),
                    'min': min(scores),
                    'max': max(scores),
                }
            else:
                report['score_summary'][key] = {}

        # 只保留前20个无效样本
        report['invalid_samples'] = report['invalid_samples'][:20]

        # 保存报告
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.logger.info(f"质量报告已保存到: {output_path}")

        # 输出摘要
        valid_ratio = report['valid'] / report['total'] * 100 if report['total'] > 0 else 0
        self.logger.info(f"质量报告摘要: {report['valid']}/{report['total']} 有效 ({valid_ratio:.1f}%)")
