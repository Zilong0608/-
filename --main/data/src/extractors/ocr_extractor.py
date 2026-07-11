# -*- coding: utf-8 -*-
"""
OCR文本提取器
用于扫描版PDF和图片文件
"""

from pathlib import Path
from typing import List, Optional
import tempfile
import os

from .base import BaseExtractor, ExtractedDocument, ExtractedPage
from ..utils.logger import get_logger


class OCRExtractor(BaseExtractor):
    """OCR文本提取器"""

    def __init__(self, engine: str = 'easyocr', lang: str = 'ch'):
        """
        初始化OCR提取器

        Args:
            engine: OCR引擎，'paddleocr', 'tesseract' 或 'easyocr'
            lang: 语言，'ch' 中文，'en' 英文
        """
        super().__init__()
        self.supported_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        self.engine = engine
        self.lang = lang
        self.logger = get_logger("ocr_extractor")

        self._ocr_instance = None

    def _get_paddleocr(self):
        """延迟加载PaddleOCR"""
        if self._ocr_instance is None and self.engine == 'paddleocr':
            # 禁用OneDNN以避免兼容性问题
            os.environ['PADDLE_USE_ONEDNN'] = '0'
            os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

            from paddleocr import PaddleOCR
            import logging
            # 抑制PaddleOCR日志
            logging.getLogger('ppocr').setLevel(logging.WARNING)
            logging.getLogger('paddlex').setLevel(logging.WARNING)
            self._ocr_instance = PaddleOCR(lang=self.lang, use_angle_cls=False, use_gpu=False)
        return self._ocr_instance

    def _get_easyocr(self):
        """延迟加载EasyOCR"""
        if self._ocr_instance is None and self.engine == 'easyocr':
            import easyocr
            # EasyOCR语言代码映射
            lang_map = {'ch': ['ch_sim', 'en'], 'en': ['en']}
            langs = lang_map.get(self.lang, ['ch_sim', 'en'])
            self._ocr_instance = easyocr.Reader(langs, gpu=False)
        return self._ocr_instance

    def extract(self, file_path: Path) -> ExtractedDocument:
        """提取图片中的文本"""
        file_path = Path(file_path)

        if not file_path.exists():
            return self._create_error_document(file_path, f"文件不存在: {file_path}")

        try:
            if self.engine == 'paddleocr':
                return self._extract_with_paddleocr(file_path)
            elif self.engine == 'tesseract':
                return self._extract_with_tesseract(file_path)
            elif self.engine == 'easyocr':
                return self._extract_with_easyocr(file_path)
            else:
                return self._create_error_document(
                    file_path, f"不支持的OCR引擎: {self.engine}"
                )
        except Exception as e:
            self.logger.error(f"OCR提取失败 {file_path}: {e}")
            return self._create_error_document(file_path, str(e))

    def _extract_with_paddleocr(self, file_path: Path) -> ExtractedDocument:
        """使用PaddleOCR提取"""
        ocr = self._get_paddleocr()

        # 新版PaddleOCR使用predict方法
        try:
            result = ocr.predict(str(file_path))
        except (TypeError, AttributeError):
            # 兼容旧版API
            result = ocr.ocr(str(file_path))

        # 提取文本
        texts = []
        if result:
            # 新版返回格式可能不同，尝试多种解析方式
            if isinstance(result, dict) and 'rec_texts' in result:
                # 新版格式
                texts = result.get('rec_texts', [])
            elif isinstance(result, list):
                # 旧版格式
                for page_result in result:
                    if page_result:
                        for line in page_result:
                            if line and len(line) >= 2:
                                text = line[1][0] if isinstance(line[1], (list, tuple)) else line[1]
                                texts.append(str(text))

        full_text = '\n'.join(texts)
        full_text = self._clean_text(full_text)

        pages = [ExtractedPage(
            page_num=1,
            content=full_text,
            has_images=True,
            has_tables=False,
        )]

        return ExtractedDocument(
            source_path=file_path,
            file_name=file_path.name,
            file_type=file_path.suffix.lower(),
            pages=pages,
            full_text=full_text,
            metadata={
                'engine': 'paddleocr',
                'lang': self.lang,
            },
        )

    def _extract_with_tesseract(self, file_path: Path) -> ExtractedDocument:
        """使用Tesseract提取"""
        import pytesseract
        from PIL import Image

        # 设置语言
        lang_map = {'ch': 'chi_sim', 'en': 'eng'}
        tess_lang = lang_map.get(self.lang, 'chi_sim+eng')

        image = Image.open(file_path)
        text = pytesseract.image_to_string(image, lang=tess_lang)
        text = self._clean_text(text)

        pages = [ExtractedPage(
            page_num=1,
            content=text,
            has_images=True,
            has_tables=False,
        )]

        return ExtractedDocument(
            source_path=file_path,
            file_name=file_path.name,
            file_type=file_path.suffix.lower(),
            pages=pages,
            full_text=text,
            metadata={
                'engine': 'tesseract',
                'lang': tess_lang,
            },
        )

    def _extract_with_easyocr(self, file_path: Path) -> ExtractedDocument:
        """使用EasyOCR提取"""
        reader = self._get_easyocr()

        # 读取图片并进行OCR
        result = reader.readtext(str(file_path))

        # EasyOCR返回格式: [(bbox, text, confidence), ...]
        texts = [text for (bbox, text, conf) in result]
        full_text = '\n'.join(texts)
        full_text = self._clean_text(full_text)

        pages = [ExtractedPage(
            page_num=1,
            content=full_text,
            has_images=True,
            has_tables=False,
        )]

        return ExtractedDocument(
            source_path=file_path,
            file_name=file_path.name,
            file_type=file_path.suffix.lower(),
            pages=pages,
            full_text=full_text,
            metadata={
                'engine': 'easyocr',
                'lang': self.lang,
            },
        )

    def extract_from_pdf_images(self, pdf_path: Path) -> ExtractedDocument:
        """
        从扫描版PDF中提取文本（先转图片再OCR）

        Args:
            pdf_path: PDF文件路径

        Returns:
            提取的文档
        """
        import fitz  # PyMuPDF
        import time

        # 抑制MuPDF警告
        fitz.TOOLS.mupdf_display_errors(False)

        pdf_path = Path(pdf_path)
        pages = []
        all_text = []

        try:
            with fitz.open(pdf_path) as doc:
                for page_num, page in enumerate(doc, 1):
                    # 将页面渲染为图片
                    pix = page.get_pixmap(dpi=150)  # 降低DPI加快速度

                    # 使用唯一文件名避免冲突
                    tmp_path = os.path.join(
                        tempfile.gettempdir(),
                        f"ocr_{os.getpid()}_{page_num}_{int(time.time()*1000)}.png"
                    )

                    try:
                        pix.save(tmp_path)

                        # OCR识别
                        if self.engine == 'paddleocr':
                            page_doc = self._extract_with_paddleocr(Path(tmp_path))
                        elif self.engine == 'easyocr':
                            page_doc = self._extract_with_easyocr(Path(tmp_path))
                        else:
                            page_doc = self._extract_with_tesseract(Path(tmp_path))

                        text = page_doc.full_text

                        pages.append(ExtractedPage(
                            page_num=page_num,
                            content=text,
                            has_images=True,
                            has_tables=False,
                        ))
                        all_text.append(text)

                    finally:
                        # 删除临时文件（忽略权限错误）
                        try:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                        except:
                            pass

            full_text = '\n\n'.join(all_text)

            return ExtractedDocument(
                source_path=pdf_path,
                file_name=pdf_path.name,
                file_type='.pdf',
                pages=pages,
                full_text=full_text,
                metadata={
                    'engine': f'ocr_{self.engine}',
                    'is_scanned': True,
                },
            )

        except Exception as e:
            self.logger.error(f"OCR提取PDF失败 {pdf_path}: {e}")
            return self._create_error_document(pdf_path, str(e))
