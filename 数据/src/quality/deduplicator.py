# -*- coding: utf-8 -*-
"""
去重器
基于相似度去除重复的chunks
"""

import re
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
import hashlib

from ..utils.logger import get_logger
from ..config.settings import QualityConfig
from ..parsers.chunker import Chunk


class Deduplicator:
    """去重器"""

    def __init__(self, config: Optional[QualityConfig] = None):
        """
        初始化去重器

        Args:
            config: 质量配置
        """
        self.config = config or QualityConfig()
        self.logger = get_logger("deduplicator")

    def deduplicate(
        self,
        chunks: List[Chunk],
        threshold: Optional[float] = None
    ) -> Tuple[List[Chunk], List[Tuple[str, str]]]:
        """
        去除重复chunks

        Args:
            chunks: chunk列表
            threshold: 相似度阈值

        Returns:
            (去重后的chunks, 被移除的重复对列表)
        """
        threshold = threshold or self.config.dedup_threshold

        # 第一阶段：精确去重（基于hash）
        chunks, exact_dups = self._exact_dedup(chunks)

        # 第二阶段：相似度去重（暂时跳过，数据量大时O(n²)算法太慢）
        # TODO: 使用更高效的算法（如LSH或MinHash）来处理大规模数据去重
        # chunks, similar_dups = self._similarity_dedup(chunks, threshold)
        similar_dups = []  # 跳过相似度去重

        all_dups = exact_dups + similar_dups

        self.logger.info(
            f"去重完成: 移除 {len(all_dups)} 个重复 "
            f"(精确: {len(exact_dups)}, 相似: {len(similar_dups)})"
        )

        return chunks, all_dups

    def _exact_dedup(
        self,
        chunks: List[Chunk]
    ) -> Tuple[List[Chunk], List[Tuple[str, str]]]:
        """
        精确去重（基于内容hash）

        Args:
            chunks: chunk列表

        Returns:
            (去重后的chunks, 重复对列表)
        """
        seen_hashes: Dict[str, Chunk] = {}
        unique_chunks = []
        duplicates = []

        for chunk in chunks:
            # 计算内容hash
            content_hash = self._compute_hash(chunk.content)

            if content_hash in seen_hashes:
                # 找到重复，保留较长的那个
                existing = seen_hashes[content_hash]
                if len(chunk.content) > len(existing.content):
                    # 替换
                    duplicates.append((existing.chunk_id, chunk.chunk_id))
                    seen_hashes[content_hash] = chunk
                    unique_chunks = [c for c in unique_chunks if c.chunk_id != existing.chunk_id]
                    unique_chunks.append(chunk)
                else:
                    duplicates.append((chunk.chunk_id, existing.chunk_id))
            else:
                seen_hashes[content_hash] = chunk
                unique_chunks.append(chunk)

        return unique_chunks, duplicates

    def _similarity_dedup(
        self,
        chunks: List[Chunk],
        threshold: float
    ) -> Tuple[List[Chunk], List[Tuple[str, str]]]:
        """
        相似度去重

        Args:
            chunks: chunk列表
            threshold: 相似度阈值

        Returns:
            (去重后的chunks, 重复对列表)
        """
        if len(chunks) <= 1:
            return chunks, []

        # 计算所有chunk的特征
        chunk_features = {}
        for chunk in chunks:
            features = self._extract_features(chunk.content)
            chunk_features[chunk.chunk_id] = features

        # 找出相似对
        duplicates = []
        to_remove: Set[str] = set()

        for i, chunk1 in enumerate(chunks):
            if chunk1.chunk_id in to_remove:
                continue

            for chunk2 in chunks[i+1:]:
                if chunk2.chunk_id in to_remove:
                    continue

                # 计算相似度
                sim = self._compute_similarity(
                    chunk_features[chunk1.chunk_id],
                    chunk_features[chunk2.chunk_id]
                )

                if sim >= threshold:
                    # 保留较长/较完整的那个
                    if self._should_keep_first(chunk1, chunk2):
                        to_remove.add(chunk2.chunk_id)
                        duplicates.append((chunk2.chunk_id, chunk1.chunk_id))
                    else:
                        to_remove.add(chunk1.chunk_id)
                        duplicates.append((chunk1.chunk_id, chunk2.chunk_id))
                        break  # chunk1被移除，跳出内层循环

        unique_chunks = [c for c in chunks if c.chunk_id not in to_remove]

        return unique_chunks, duplicates

    def _compute_hash(self, text: str) -> str:
        """计算文本hash"""
        # 规范化文本
        normalized = self._normalize_text(text)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def _normalize_text(self, text: str) -> str:
        """规范化文本（用于去重比较）"""
        # 转小写
        text = text.lower()
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 移除标点
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
        return text.strip()

    def _extract_features(self, text: str) -> Dict:
        """
        提取文本特征（用于相似度计算）

        Args:
            text: 输入文本

        Returns:
            特征字典
        """
        normalized = self._normalize_text(text)

        # 提取n-gram
        words = normalized.split()
        bigrams = set()
        trigrams = set()

        for i in range(len(words) - 1):
            bigrams.add((words[i], words[i+1]))
        for i in range(len(words) - 2):
            trigrams.add((words[i], words[i+1], words[i+2]))

        # 提取字符n-gram（对中文更有效）
        char_bigrams = set()
        for i in range(len(normalized) - 1):
            char_bigrams.add(normalized[i:i+2])

        return {
            'words': set(words),
            'bigrams': bigrams,
            'trigrams': trigrams,
            'char_bigrams': char_bigrams,
            'length': len(text),
        }

    def _compute_similarity(self, features1: Dict, features2: Dict) -> float:
        """
        计算两个特征集的相似度

        Args:
            features1: 特征1
            features2: 特征2

        Returns:
            相似度 (0-1)
        """
        scores = []

        # 词级Jaccard相似度
        if features1['words'] and features2['words']:
            intersection = len(features1['words'] & features2['words'])
            union = len(features1['words'] | features2['words'])
            scores.append(intersection / union if union > 0 else 0)

        # 字符bigram相似度
        if features1['char_bigrams'] and features2['char_bigrams']:
            intersection = len(features1['char_bigrams'] & features2['char_bigrams'])
            union = len(features1['char_bigrams'] | features2['char_bigrams'])
            scores.append(intersection / union if union > 0 else 0)

        # bigram相似度
        if features1['bigrams'] and features2['bigrams']:
            intersection = len(features1['bigrams'] & features2['bigrams'])
            union = len(features1['bigrams'] | features2['bigrams'])
            scores.append(intersection / union if union > 0 else 0)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    def _should_keep_first(self, chunk1: Chunk, chunk2: Chunk) -> bool:
        """
        判断应该保留哪个chunk

        Args:
            chunk1: 候选1
            chunk2: 候选2

        Returns:
            True表示保留chunk1，False表示保留chunk2
        """
        # 优先保留Q&A类型
        if chunk1.chunk_type == 'qa' and chunk2.chunk_type != 'qa':
            return True
        if chunk2.chunk_type == 'qa' and chunk1.chunk_type != 'qa':
            return False

        # 优先保留更长的
        if len(chunk1.content) > len(chunk2.content) * 1.1:
            return True
        if len(chunk2.content) > len(chunk1.content) * 1.1:
            return False

        # 优先保留有更多metadata的
        if len(chunk1.metadata) > len(chunk2.metadata):
            return True
        if len(chunk2.metadata) > len(chunk1.metadata):
            return False

        # 默认保留第一个
        return True

    def find_duplicates_across_files(
        self,
        chunks: List[Chunk]
    ) -> Dict[str, List[str]]:
        """
        查找跨文件的重复

        Args:
            chunks: chunk列表

        Returns:
            {源文件: [重复的chunk_ids]}
        """
        # 按内容分组
        content_groups: Dict[str, List[Chunk]] = defaultdict(list)

        for chunk in chunks:
            content_hash = self._compute_hash(chunk.content)
            content_groups[content_hash].append(chunk)

        # 找出跨文件重复
        cross_file_dups: Dict[str, List[str]] = defaultdict(list)

        for content_hash, group in content_groups.items():
            if len(group) <= 1:
                continue

            # 检查是否来自不同文件
            files = set(c.source_file for c in group if c.source_file)
            if len(files) > 1:
                for chunk in group:
                    if chunk.source_file:
                        cross_file_dups[chunk.source_file].append(chunk.chunk_id)

        return dict(cross_file_dups)
