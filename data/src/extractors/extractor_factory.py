# -*- coding: utf-8 -*-
"""
提取器工厂
根据文件类型自动选择合适的提取器
"""

from pathlib import Path
from typing import Optional, Dict, Type

from .base import BaseExtractor, ExtractedDocument
from .pdf_extractor import PDFExtractor
from .doc_extractor import DocExtractor
from .markdown_extractor import MarkdownExtractor
from .ocr_extractor import OCRExtractor
from ..utils.logger import get_logger
from ..config.settings import ExtractorConfig


class ExtractorFactory:
    """提取器工厂"""

    def __init__(self, config: Optional[ExtractorConfig] = None):
        """
        初始化工厂

        Args:
            config: 提取器配置
        """
        self.config = config or ExtractorConfig()
        self.logger = get_logger("extractor_factory")

        # 初始化各类提取器
        self._extractors: Dict[str, BaseExtractor] = {}
        self._init_extractors()

    def _init_extractors(self):
        """初始化所有提取器"""
        # PDF提取器
        pdf_extractor = PDFExtractor(engine=self.config.pdf_extractor)
        for ext in pdf_extractor.supported_extensions:
            self._extractors[ext] = pdf_extractor

        # Word文档提取器
        doc_extractor = DocExtractor()
        for ext in doc_extractor.supported_extensions:
            self._extractors[ext] = doc_extractor

        # Markdown/文本提取器
        md_extractor = MarkdownExtractor()
        for ext in md_extractor.supported_extensions:
            self._extractors[ext] = md_extractor

        # OCR提取器（用于图片）
        if self.config.enable_ocr:
            ocr_extractor = OCRExtractor(
                engine=self.config.ocr_engine,
                lang=self.config.ocr_lang
            )
            for ext in ocr_extractor.supported_extensions:
                self._extractors[ext] = ocr_extractor

    def get_extractor(self, file_path: Path) -> Optional[BaseExtractor]:
        """
        根据文件获取对应的提取器

        Args:
            file_path: 文件路径

        Returns:
            合适的提取器，如果不支持则返回None
        """
        suffix = Path(file_path).suffix.lower()
        return self._extractors.get(suffix)

    def extract(self, file_path: Path) -> ExtractedDocument:
        """
        提取文件内容

        Args:
            file_path: 文件路径

        Returns:
            提取的文档对象
        """
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        extractor = self.get_extractor(file_path)

        if extractor is None:
            self.logger.warning(f"不支持的文件格式: {suffix}")
            return ExtractedDocument(
                source_path=file_path,
                file_name=file_path.name,
                file_type=suffix,
                pages=[],
                full_text="",
                errors=[f"不支持的文件格式: {suffix}"],
            )

        self.logger.debug(f"使用 {extractor.__class__.__name__} 提取: {file_path.name}")
        doc = extractor.extract(file_path)

        # 扫描版PDF不做OCR，避免内容丢失
        if (suffix == '.pdf' and
            doc.metadata.get('is_scanned', False) and
            not doc.has_errors):
            self.logger.warning(f"检测到扫描版PDF，已跳过OCR: {file_path.name}")

        return doc

    def can_extract(self, file_path: Path) -> bool:
        """
        检查是否能提取该文件

        Args:
            file_path: 文件路径

        Returns:
            是否支持
        """
        return self.get_extractor(file_path) is not None

    @property
    def supported_extensions(self) -> list:
        """获取所有支持的扩展名"""
        return list(self._extractors.keys())
