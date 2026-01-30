# -*- coding: utf-8 -*-
"""
Metadata标注器
为chunks添加岗位、难度、问题类型等标签
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from ..utils.logger import get_logger
from ..config.settings import MetadataConfig
from ..parsers.chunker import Chunk


class MetadataLabeler:
    """Metadata标注器"""

    def __init__(self, config: Optional[MetadataConfig] = None):
        """
        初始化标注器

        Args:
            config: Metadata配置
        """
        self.config = config or MetadataConfig()
        self.logger = get_logger("metadata_labeler")

    def label_chunk(self, chunk: Chunk) -> Chunk:
        """
        为单个chunk添加标签

        Args:
            chunk: 输入chunk

        Returns:
            添加标签后的chunk
        """
        # 标注内容分类（面试题/笔试题/面试技巧/其他）
        content_category = self._label_content_category(chunk)

        # 标注岗位/领域
        position = self._label_position(chunk)

        # 标注难度
        difficulty = self._label_difficulty(chunk)

        # 标注问题类型
        question_type = self._label_question_type(chunk)

        # 更新metadata
        chunk.metadata.update({
            'content_category': content_category,
            'position': position,
            'difficulty': difficulty,
            'question_type': question_type,
        })

        return chunk

    def _label_content_category(self, chunk: Chunk) -> str:
        """
        标注内容分类

        Returns:
            '面试题' | '笔试题' | '面试技巧' | '其他'
        """
        if not chunk.source_file:
            return '面试题'  # 默认

        path_str = str(chunk.source_file)

        # 优先级：其他 > 笔试题 > 面试技巧 > 面试题
        # （因为简历模板不应该被当成面试题）

        # 检查是否是简历/其他
        for pattern in self.config.other_patterns:
            if pattern in path_str:
                return '其他'

        # 检查是否是笔试题
        for pattern in self.config.written_test_patterns:
            if pattern in path_str:
                return '笔试题'

        # 检查是否是面试技巧
        for pattern in self.config.interview_tips_patterns:
            if pattern in path_str:
                return '面试技巧'

        # 检查是否是面试题
        for pattern in self.config.interview_question_patterns:
            if pattern in path_str:
                return '面试题'

        # 默认根据内容判断
        content = chunk.content.lower() if chunk.content else ''

        # 如果内容像Q&A格式，认为是面试题
        if chunk.question and chunk.answer:
            return '面试题'

        return '面试题'  # 默认

    def label_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        批量标注chunks

        Args:
            chunks: chunk列表

        Returns:
            标注后的chunk列表
        """
        for chunk in chunks:
            self.label_chunk(chunk)
        return chunks

    def _label_position(self, chunk: Chunk) -> str:
        """标注岗位/领域"""
        # 首先根据来源文件路径判断
        if chunk.source_file:
            source_path = Path(chunk.source_file)

            # 遍历路径部分，查找匹配的岗位
            for part in source_path.parts:
                if part in self.config.position_mapping:
                    return self.config.position_mapping[part]

            # 模糊匹配
            path_str = str(source_path)
            for folder, position in self.config.position_mapping.items():
                if folder in path_str:
                    return position

        # 根据内容关键词判断
        content = chunk.content.lower()

        position_keywords = {
            'AI大模型': ['大模型', 'llm', 'transformer', 'gpt', 'bert', 'attention', 'chatgpt', '预训练'],
            '深度学习': ['深度学习', 'cnn', 'rnn', 'lstm', '神经网络', '卷积', '反向传播'],
            '网络安全': ['渗透', '漏洞', 'xss', 'sql注入', '防火墙', '安全', 'webshell', '攻击'],
            '数据库': ['mysql', 'oracle', 'sql', '索引', '事务', '数据库', 'redis', 'mongodb'],
            '数据分析': ['数据分析', 'pandas', '可视化', '统计', '数据挖掘', 'excel'],
            '算法': ['算法', '数据结构', '排序', '动态规划', '贪心', '图算法'],
            '测试开发': ['测试', '自动化', 'selenium', 'pytest', 'unittest', '单元测试'],
        }

        for position, keywords in position_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    return position

        return '通用'

    def _label_difficulty(self, chunk: Chunk) -> str:
        """标注难度级别"""
        content = chunk.content.lower()

        # 检查各难度级别的关键词
        for difficulty, keywords in self.config.difficulty_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    return difficulty

        # 根据内容复杂度估算
        # 如果涉及源码、底层原理等，认为是高级
        high_level_indicators = [
            '源码', '底层', '实现原理', '架构设计', '性能优化',
            '分布式', '高并发', '系统设计', '源代码'
        ]
        for indicator in high_level_indicators:
            if indicator in content:
                return '高级'

        # 如果是简单定义或概念，认为是基础
        if chunk.question:
            question = chunk.question.lower()
            basic_indicators = ['是什么', '什么是', '定义', '简单介绍', '概念']
            for indicator in basic_indicators:
                if indicator in question:
                    return '基础'

        return '进阶'  # 默认中等难度

    def _label_question_type(self, chunk: Chunk) -> str:
        """标注问题类型"""
        if not chunk.question:
            return '知识点'

        question = chunk.question.lower()

        for q_type, keywords in self.config.question_type_keywords.items():
            for keyword in keywords:
                if keyword in question:
                    return q_type

        # 根据答案内容辅助判断
        if chunk.answer:
            answer = chunk.answer.lower()

            # 如果答案中有代码，可能是代码题
            if '```' in answer or 'def ' in answer or 'function' in answer:
                return '代码题'

            # 如果答案是列表形式，可能是对比题
            if answer.count('\n-') > 3 or answer.count('\n•') > 3:
                return '对比题'

        return '概念题'

    def add_custom_labels(
        self,
        chunk: Chunk,
        labels: Dict[str, Any]
    ) -> Chunk:
        """
        添加自定义标签

        Args:
            chunk: 输入chunk
            labels: 自定义标签字典

        Returns:
            更新后的chunk
        """
        chunk.metadata.update(labels)
        return chunk

    def get_statistics(self, chunks: List[Chunk]) -> Dict:
        """
        获取标注统计信息

        Args:
            chunks: chunk列表

        Returns:
            统计信息
        """
        stats = {
            'total': len(chunks),
            'by_content_category': {},
            'by_position': {},
            'by_difficulty': {},
            'by_question_type': {},
        }

        for chunk in chunks:
            # 按内容分类统计
            cat = chunk.metadata.get('content_category', '未标注')
            stats['by_content_category'][cat] = stats['by_content_category'].get(cat, 0) + 1

            # 按岗位统计
            pos = chunk.metadata.get('position', '未标注')
            stats['by_position'][pos] = stats['by_position'].get(pos, 0) + 1

            # 按难度统计
            diff = chunk.metadata.get('difficulty', '未标注')
            stats['by_difficulty'][diff] = stats['by_difficulty'].get(diff, 0) + 1

            # 按问题类型统计
            q_type = chunk.metadata.get('question_type', '未标注')
            stats['by_question_type'][q_type] = stats['by_question_type'].get(q_type, 0) + 1

        return stats
