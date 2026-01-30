# -*- coding: utf-8 -*-
"""
文本提取器基类
"""

from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class ExtractedPage:
    """提取的单页内容"""
    page_num: int
    content: str
    has_images: bool = False
    has_tables: bool = False


@dataclass
class ExtractedDocument:
    """提取的文档内容"""
    source_path: Path
    file_name: str
    file_type: str
    pages: List[ExtractedPage]
    full_text: str
    extraction_time: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return len(self.full_text)

    @property
    def is_empty(self) -> bool:
        return len(self.full_text.strip()) == 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def to_dict(self) -> dict:
        return {
            'source_path': str(self.source_path),
            'file_name': self.file_name,
            'file_type': self.file_type,
            'page_count': self.page_count,
            'char_count': self.char_count,
            'full_text': self.full_text,
            'pages': [
                {
                    'page_num': p.page_num,
                    'content': p.content,
                    'has_images': p.has_images,
                    'has_tables': p.has_tables,
                }
                for p in self.pages
            ],
            'extraction_time': self.extraction_time.isoformat(),
            'metadata': self.metadata,
            'errors': self.errors,
        }


class BaseExtractor(ABC):
    """文本提取器基类"""

    def __init__(self):
        self.supported_extensions: List[str] = []

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractedDocument:
        """
        提取文件内容

        Args:
            file_path: 文件路径

        Returns:
            提取的文档对象
        """
        pass

    def can_handle(self, file_path: Path) -> bool:
        """
        判断是否能处理该文件

        Args:
            file_path: 文件路径

        Returns:
            是否能处理
        """
        return file_path.suffix.lower() in self.supported_extensions

    def _clean_text(self, text: str) -> str:
        """
        清理文本

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        if not text:
            return ""

        # 替换特殊空白字符
        text = text.replace('\x00', '')
        text = text.replace('\r\n', '\n')
        text = text.replace('\r', '\n')

        # 合并多个连续空行为两个
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 去除行首行尾多余空格（保留换行结构）
        lines = text.split('\n')
        lines = [line.strip() for line in lines]
        text = '\n'.join(lines)

        return text.strip()

    def _create_error_document(
        self,
        file_path: Path,
        error_msg: str
    ) -> ExtractedDocument:
        """
        创建错误文档对象

        Args:
            file_path: 文件路径
            error_msg: 错误信息

        Returns:
            带错误信息的文档对象
        """
        return ExtractedDocument(
            source_path=file_path,
            file_name=file_path.name,
            file_type=file_path.suffix.lower(),
            pages=[],
            full_text="",
            errors=[error_msg],
        )
