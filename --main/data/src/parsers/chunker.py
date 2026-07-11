# -*- coding: utf-8 -*-
"""
文本分块器
将解析后的Q&A进一步处理，生成适合向量检索的chunks
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from ..utils.logger import get_logger
from ..config.settings import ChunkerConfig
from .qa_parser import QAPair


@dataclass
class Chunk:
    """文本块"""
    chunk_id: str
    content: str
    question: Optional[str] = None  # 如果是Q&A，记录问题
    answer: Optional[str] = None  # 如果是Q&A，记录答案
    chunk_type: str = 'qa'  # 'qa' 或 'text'
    source_file: Optional[str] = None
    page_num: Optional[int] = None
    question_num: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.content)

    def to_dict(self) -> dict:
        return {
            'chunk_id': self.chunk_id,
            'content': self.content,
            'question': self.question,
            'answer': self.answer,
            'chunk_type': self.chunk_type,
            'source_file': self.source_file,
            'page_num': self.page_num,
            'question_num': self.question_num,
            'char_count': self.char_count,
            'metadata': self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Chunk':
        data.pop('char_count', None)  # 移除计算属性
        return cls(**data)


class Chunker:
    """文本分块器"""

    def __init__(self, config: Optional[ChunkerConfig] = None):
        """
        初始化分块器

        Args:
            config: 分块配置
        """
        self.config = config or ChunkerConfig()
        self.logger = get_logger("chunker")
        self._chunk_counter = 0

    def _generate_chunk_id(self, prefix: str = "chunk") -> str:
        """生成chunk ID"""
        self._chunk_counter += 1
        return f"{prefix}_{self._chunk_counter:06d}"

    def chunk_qa_pairs(
        self,
        qa_pairs: List[QAPair],
        source_file: Optional[str] = None
    ) -> List[Chunk]:
        """
        将Q&A对转换为chunks

        Args:
            qa_pairs: 问答对列表
            source_file: 来源文件

        Returns:
            chunk列表
        """
        chunks = []

        for qa in qa_pairs:
            # 如果Q&A太长，需要切分答案
            if qa.char_count > self.config.max_chunk_size:
                sub_chunks = self._split_long_qa(qa, source_file)
                chunks.extend(sub_chunks)
            else:
                chunk = Chunk(
                    chunk_id=self._generate_chunk_id("qa"),
                    content=qa.full_text,
                    question=qa.question,
                    answer=qa.answer,
                    chunk_type='qa',
                    source_file=source_file or qa.source_file,
                    page_num=qa.page_num,
                    question_num=qa.question_num,
                )
                chunks.append(chunk)

        return chunks

    def _split_long_qa(
        self,
        qa: QAPair,
        source_file: Optional[str] = None
    ) -> List[Chunk]:
        """
        切分过长的Q&A

        Args:
            qa: 问答对
            source_file: 来源文件

        Returns:
            chunk列表
        """
        chunks = []
        question = qa.question
        answer = qa.answer

        # 首先尝试按段落切分答案
        paragraphs = re.split(r'\n\s*\n', answer)

        current_content = question + "\n\n"
        current_answer_parts = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 检查加入这段后是否超长
            test_content = current_content + para
            if len(test_content) > self.config.max_chunk_size and current_answer_parts:
                # 保存当前chunk
                chunk = Chunk(
                    chunk_id=self._generate_chunk_id("qa"),
                    content=current_content.strip(),
                    question=question,
                    answer='\n\n'.join(current_answer_parts),
                    chunk_type='qa',
                    source_file=source_file or qa.source_file,
                    page_num=qa.page_num,
                    question_num=qa.question_num,
                    metadata={'is_split': True, 'part': len(chunks) + 1},
                )
                chunks.append(chunk)

                # 开始新的chunk（带重叠：保留问题作为上下文）
                overlap = self._get_overlap_text(current_answer_parts)
                current_content = question + "\n\n（续）\n\n" + overlap
                current_answer_parts = [para] if overlap else [para]
                current_content += para + "\n\n"
            else:
                current_content += para + "\n\n"
                current_answer_parts.append(para)

        # 保存最后一个chunk
        if current_answer_parts:
            chunk = Chunk(
                chunk_id=self._generate_chunk_id("qa"),
                content=current_content.strip(),
                question=question,
                answer='\n\n'.join(current_answer_parts),
                chunk_type='qa',
                source_file=source_file or qa.source_file,
                page_num=qa.page_num,
                question_num=qa.question_num,
                metadata={
                    'is_split': len(chunks) > 0,
                    'part': len(chunks) + 1 if chunks else None
                },
            )
            chunks.append(chunk)

        return chunks

    def _get_overlap_text(self, parts: List[str]) -> str:
        """获取重叠文本"""
        if not parts:
            return ""

        # 取最后一段的部分作为重叠
        last_part = parts[-1]
        if len(last_part) <= self.config.overlap_size:
            return last_part

        # 尝试在句子边界切分
        sentences = re.split(r'[。！？.!?]', last_part)
        overlap = ""
        for sent in reversed(sentences):
            if len(overlap) + len(sent) <= self.config.overlap_size:
                overlap = sent + "。" + overlap
            else:
                break

        return overlap.strip() or last_part[-self.config.overlap_size:]

    def chunk_plain_text(
        self,
        text: str,
        source_file: Optional[str] = None,
        page_num: Optional[int] = None
    ) -> List[Chunk]:
        """
        对纯文本进行分块（非Q&A格式的文本）

        Args:
            text: 输入文本
            source_file: 来源文件
            page_num: 页码

        Returns:
            chunk列表
        """
        if not text or not text.strip():
            return []

        chunks = []
        paragraphs = re.split(r'\n\s*\n', text)

        current_content = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_content) + len(para) > self.config.max_chunk_size:
                if current_content:
                    chunk = Chunk(
                        chunk_id=self._generate_chunk_id("text"),
                        content=current_content.strip(),
                        chunk_type='text',
                        source_file=source_file,
                        page_num=page_num,
                    )
                    chunks.append(chunk)

                    # 重叠
                    overlap = current_content[-self.config.overlap_size:] if len(current_content) > self.config.overlap_size else ""
                    current_content = overlap + "\n\n" + para + "\n\n"
                else:
                    # 单段就超长，强制切分
                    sub_chunks = self._force_split(para, source_file, page_num)
                    chunks.extend(sub_chunks)
                    current_content = ""
            else:
                current_content += para + "\n\n"

        # 保存最后一个chunk
        if current_content.strip():
            chunk = Chunk(
                chunk_id=self._generate_chunk_id("text"),
                content=current_content.strip(),
                chunk_type='text',
                source_file=source_file,
                page_num=page_num,
            )
            chunks.append(chunk)

        return chunks

    def chunk_markdown(
        self,
        text: str,
        source_file: Optional[str] = None,
        page_num: Optional[int] = None
    ) -> List[Chunk]:
        """
        对Markdown文本进行分块（优先按标题拆分）
        """
        if not text or not text.strip():
            return []

        lines = text.splitlines()
        sections = []
        current_title = None
        current_lines: List[str] = []

        for line in lines:
            if line.strip().startswith("#"):
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines).strip()))
                current_title = line.strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_title, "\n".join(current_lines).strip()))

        if len(sections) == 1 and not sections[0][0]:
            return self.chunk_plain_text(text, source_file, page_num)

        chunks: List[Chunk] = []
        for title, body in sections:
            section_text = (title + "\n\n" + body).strip() if title else body.strip()
            if not section_text:
                continue

            if len(section_text) > self.config.max_chunk_size:
                sub_chunks = self._force_split(section_text, source_file, page_num)
                for sub in sub_chunks:
                    if title:
                        sub.metadata['md_title'] = title
                        sub.metadata['md_section'] = True
                chunks.extend(sub_chunks)
            else:
                chunk = Chunk(
                    chunk_id=self._generate_chunk_id("md"),
                    content=section_text,
                    chunk_type='text',
                    source_file=source_file,
                    page_num=page_num,
                    metadata={'md_title': title} if title else {},
                )
                chunks.append(chunk)

        return chunks

    def _force_split(
        self,
        text: str,
        source_file: Optional[str],
        page_num: Optional[int]
    ) -> List[Chunk]:
        """强制切分超长文本"""
        chunks = []
        max_size = self.config.max_chunk_size
        overlap = self.config.overlap_size

        start = 0
        while start < len(text):
            end = start + max_size

            # 尝试在句子边界切分
            if end < len(text):
                # 向前找句子结束符
                for i in range(end, max(start + max_size // 2, start), -1):
                    if text[i] in '。！？.!?\n':
                        end = i + 1
                        break

            chunk_text = text[start:end]

            chunk = Chunk(
                chunk_id=self._generate_chunk_id("text"),
                content=chunk_text.strip(),
                chunk_type='text',
                source_file=source_file,
                page_num=page_num,
                metadata={'force_split': True},
            )
            chunks.append(chunk)

            start = end - overlap if end < len(text) else end

        return chunks

    def filter_short_chunks(
        self,
        chunks: List[Chunk],
        min_length: Optional[int] = None
    ) -> List[Chunk]:
        """
        过滤过短的chunks

        Args:
            chunks: chunk列表
            min_length: 最小长度

        Returns:
            过滤后的chunk列表
        """
        min_len = min_length or self.config.min_chunk_size
        return [c for c in chunks if c.char_count >= min_len]

    def reset_counter(self):
        """重置chunk计数器"""
        self._chunk_counter = 0
