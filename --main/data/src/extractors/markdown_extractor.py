# -*- coding: utf-8 -*-
"""
Markdown和纯文本提取器
"""

from pathlib import Path

from .base import BaseExtractor, ExtractedDocument, ExtractedPage
from ..utils.logger import get_logger
from ..utils.file_utils import get_file_encoding


class MarkdownExtractor(BaseExtractor):
    """Markdown和纯文本提取器"""

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.md', '.txt', '.markdown', '.text']
        self.logger = get_logger("markdown_extractor")

    def extract(self, file_path: Path) -> ExtractedDocument:
        """提取Markdown/文本文件内容"""
        file_path = Path(file_path)

        if not file_path.exists():
            return self._create_error_document(file_path, f"文件不存在: {file_path}")

        try:
            # 检测文件编码
            encoding = get_file_encoding(file_path)
            self.logger.debug(f"检测到文件编码: {encoding}")

            # 读取文件
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                content = f.read()

            content = self._clean_text(content)

            # 对于Markdown，保留结构但清理不必要的格式
            if file_path.suffix.lower() in ['.md', '.markdown']:
                content = self._clean_markdown(content)

            pages = [ExtractedPage(
                page_num=1,
                content=content,
                has_images=self._has_images_md(content),
                has_tables=self._has_tables_md(content),
            )]

            return ExtractedDocument(
                source_path=file_path,
                file_name=file_path.name,
                file_type=file_path.suffix.lower(),
                pages=pages,
                full_text=content,
                metadata={
                    'encoding': encoding,
                    'engine': 'native',
                },
            )

        except Exception as e:
            self.logger.error(f"提取文件失败 {file_path}: {e}")
            return self._create_error_document(file_path, str(e))

    def _clean_markdown(self, text: str) -> str:
        """清理Markdown格式（保留结构）"""
        import re

        # 移除HTML注释
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

        # 移除多余的空行
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text

    def _has_images_md(self, content: str) -> bool:
        """检查Markdown中是否有图片引用"""
        import re
        # 匹配 ![alt](url) 或 <img> 标签
        return bool(re.search(r'!\[.*?\]\(.*?\)|<img.*?>', content))

    def _has_tables_md(self, content: str) -> bool:
        """检查Markdown中是否有表格"""
        import re
        # 匹配Markdown表格（|---|---|模式）
        return bool(re.search(r'\|[\s-]+\|', content))
