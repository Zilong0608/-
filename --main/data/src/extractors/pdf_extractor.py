# -*- coding: utf-8 -*-
"""
PDF文本提取器
"""

from pathlib import Path
from typing import Optional
import re

from .base import BaseExtractor, ExtractedDocument, ExtractedPage
from ..utils.logger import get_logger


class PDFExtractor(BaseExtractor):
    """PDF文本提取器"""

    def __init__(self, engine: str = 'pymupdf'):
        """
        初始化PDF提取器

        Args:
            engine: 提取引擎，'pymupdf' 或 'pdfplumber'
        """
        super().__init__()
        self.supported_extensions = ['.pdf']
        self.engine = engine
        self.logger = get_logger("pdf_extractor")

    def extract(self, file_path: Path) -> ExtractedDocument:
        """提取PDF内容"""
        file_path = Path(file_path)

        if not file_path.exists():
            return self._create_error_document(file_path, f"文件不存在: {file_path}")

        try:
            if self.engine == 'pymupdf':
                return self._extract_with_pymupdf(file_path)
            elif self.engine == 'pdfplumber':
                return self._extract_with_pdfplumber(file_path)
            else:
                return self._create_error_document(
                    file_path, f"不支持的PDF引擎: {self.engine}"
                )
        except Exception as e:
            self.logger.error(f"提取PDF失败 {file_path}: {e}")
            return self._create_error_document(file_path, str(e))

    def _extract_with_pymupdf(self, file_path: Path) -> ExtractedDocument:
        """使用PyMuPDF提取"""
        import fitz  # PyMuPDF

        # 抑制MuPDF警告信息
        fitz.TOOLS.mupdf_display_errors(False)

        pages = []
        all_text = []

        with fitz.open(file_path) as doc:
            for page_num, page in enumerate(doc, 1):
                # 提取文本
                text = page.get_text("text")
                text = self._clean_text(text)

                # 检查是否有图片
                has_images = len(page.get_images()) > 0

                # 检查是否有表格（简单启发式）
                has_tables = self._detect_table(text)

                pages.append(ExtractedPage(
                    page_num=page_num,
                    content=text,
                    has_images=has_images,
                    has_tables=has_tables,
                ))

                all_text.append(text)

        full_text = '\n\n'.join(all_text)

        # 如果提取的文本太少，可能是扫描版PDF
        metadata = {
            'is_scanned': self._is_likely_scanned(full_text, len(pages)),
            'engine': 'pymupdf',
        }

        return ExtractedDocument(
            source_path=file_path,
            file_name=file_path.name,
            file_type='.pdf',
            pages=pages,
            full_text=full_text,
            metadata=metadata,
        )

    def _extract_with_pdfplumber(self, file_path: Path) -> ExtractedDocument:
        """使用pdfplumber提取"""
        import pdfplumber

        pages = []
        all_text = []

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # 提取文本
                text = page.extract_text() or ""
                text = self._clean_text(text)

                # 检查是否有图片
                has_images = len(page.images) > 0

                # 检查是否有表格
                tables = page.extract_tables()
                has_tables = len(tables) > 0

                # 如果有表格，尝试将表格转为文本
                if has_tables:
                    table_text = self._tables_to_text(tables)
                    if table_text:
                        text = text + "\n\n" + table_text

                pages.append(ExtractedPage(
                    page_num=page_num,
                    content=text,
                    has_images=has_images,
                    has_tables=has_tables,
                ))

                all_text.append(text)

        full_text = '\n\n'.join(all_text)

        metadata = {
            'is_scanned': self._is_likely_scanned(full_text, len(pages)),
            'engine': 'pdfplumber',
        }

        return ExtractedDocument(
            source_path=file_path,
            file_name=file_path.name,
            file_type='.pdf',
            pages=pages,
            full_text=full_text,
            metadata=metadata,
        )

    def _detect_table(self, text: str) -> bool:
        """简单检测文本中是否有表格"""
        # 检查是否有多个连续的制表符或大量对齐的空格
        lines = text.split('\n')
        table_like_lines = 0

        for line in lines:
            # 如果一行中有多个制表符或者有规律的空格分隔
            if '\t' in line or re.search(r'\s{3,}', line):
                table_like_lines += 1

        # 如果超过10%的行像表格，认为有表格
        return table_like_lines > len(lines) * 0.1 if lines else False

    def _tables_to_text(self, tables: list) -> str:
        """将表格转换为文本"""
        result = []

        for table in tables:
            if not table:
                continue

            table_lines = []
            for row in table:
                if row:
                    # 过滤None值并连接
                    cells = [str(cell) if cell else "" for cell in row]
                    table_lines.append(" | ".join(cells))

            if table_lines:
                result.append('\n'.join(table_lines))

        return '\n\n'.join(result)

    def _is_likely_scanned(self, text: str, page_count: int) -> bool:
        """判断是否可能是扫描版PDF"""
        if page_count == 0:
            return True

        # 平均每页字符数
        avg_chars_per_page = len(text) / page_count

        # 如果每页平均少于100个字符，可能是扫描版
        return avg_chars_per_page < 100
