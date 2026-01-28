# -*- coding: utf-8 -*-
"""
智能修复空内容文件
1. PDF先尝试直接提取文字（电子版）
2. 提取失败或文字太少才用OCR（扫描版）
3. 图片直接用OCR
4. 使用Tesseract加速
"""

import os
# 禁用OneDNN/MKLDNN以避免兼容性问题
os.environ['PADDLE_USE_ONEDNN'] = '0'
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

import sys
import json
from pathlib import Path
from tqdm import tqdm

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.extractors import OCRExtractor, PDFExtractor


def extract_text_smart(file_path, file_type, pdf_extractor, ocr_extractor, logger):
    """
    智能提取文字

    Args:
        file_path: 文件路径
        file_type: 文件类型
        pdf_extractor: PDF提取器
        ocr_extractor: OCR提取器
        logger: 日志记录器

    Returns:
        ExtractedDocument or None
    """
    try:
        # 如果是PDF，先尝试直接提取文字
        if file_type == '.pdf':
            try:
                # 方法1: 使用PDF提取器直接提取
                doc = pdf_extractor.extract(file_path)

                # 检查是否提取到了足够的文字（至少50个字符）
                if doc.full_text and len(doc.full_text.strip()) >= 50:
                    logger.info(f"✓ PDF直接提取成功: {file_path.name} ({len(doc.full_text)} 字符)")
                    return doc
                else:
                    logger.debug(f"PDF文字太少，尝试OCR: {file_path.name}")
            except Exception as e:
                logger.debug(f"PDF直接提取失败，尝试OCR: {file_path.name} - {e}")

            # 方法2: PDF直接提取失败，使用OCR
            try:
                doc = ocr_extractor.extract_from_pdf_images(file_path)
                if doc.full_text and doc.full_text.strip():
                    logger.info(f"✓ PDF OCR成功: {file_path.name} ({len(doc.full_text)} 字符)")
                    return doc
                else:
                    logger.warning(f"✗ PDF OCR无结果: {file_path.name}")
                    return None
            except Exception as e:
                logger.error(f"✗ PDF OCR失败: {file_path.name} - {e}")
                return None

        # 如果是图片，直接用OCR
        else:
            try:
                doc = ocr_extractor.extract(file_path)
                if doc.full_text and doc.full_text.strip():
                    logger.info(f"✓ 图片OCR成功: {file_path.name} ({len(doc.full_text)} 字符)")
                    return doc
                else:
                    logger.warning(f"✗ 图片OCR无结果: {file_path.name}")
                    return None
            except Exception as e:
                logger.error(f"✗ 图片OCR失败: {file_path.name} - {e}")
                return None

    except Exception as e:
        logger.error(f"处理失败 {file_path.name}: {e}")
        return None


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="fix_empty_files_smart",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("智能修复空内容文件")
    logger.info("=" * 50)

    # 加载之前的提取结果
    input_path = config.paths.data_ingest / "extracted_documents.json"
    if not input_path.exists():
        logger.error("请先运行 02_extract_text.py")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        all_docs = json.load(f)

    logger.info(f"加载了 {len(all_docs)} 个文档")

    # 找出空内容的文件（PDF和图片）
    empty_files = []
    for doc in all_docs:
        file_type = doc.get('file_type', '')
        # 只处理PDF和图片
        if file_type in ['.pdf', '.jpg', '.jpeg', '.png', '.bmp']:
            if not doc.get('error') and (not doc.get('full_text') or not doc.get('full_text').strip()):
                empty_files.append(doc)

    # 统计
    pdf_count = sum(1 for d in empty_files if d.get('file_type') == '.pdf')
    img_count = len(empty_files) - pdf_count

    logger.info(f"找到 {len(empty_files)} 个空内容文件:")
    logger.info(f"  - PDF: {pdf_count}")
    logger.info(f"  - 图片: {img_count}")

    if len(empty_files) == 0:
        logger.info("没有需要修复的文件")
        return

    # 创建提取器
    logger.info("初始化提取器...")
    pdf_extractor = PDFExtractor(engine=config.extractor.pdf_extractor)

    # 使用PaddleOCR（比EasyOCR快）
    logger.info("使用 PaddleOCR 引擎（快速模式）")
    ocr_extractor = OCRExtractor(
        engine='paddleocr',  # 使用PaddleOCR而不是EasyOCR
        lang='ch'            # 中文
    )

    # 重新提取
    fixed_count = 0
    still_empty = 0
    error_count = 0

    # 统计不同处理方式的数量
    pdf_direct_count = 0  # PDF直接提取成功
    pdf_ocr_count = 0     # PDF需要OCR
    img_ocr_count = 0     # 图片OCR

    logger.info("\n开始处理...")
    for doc in tqdm(empty_files, desc="智能提取"):
        source_path = Path(doc['source_path'])

        if not source_path.exists():
            logger.warning(f"文件不存在: {source_path}")
            error_count += 1
            continue

        file_type = doc.get('file_type')

        # 智能提取
        new_doc = extract_text_smart(source_path, file_type, pdf_extractor, ocr_extractor, logger)

        if new_doc and new_doc.full_text and new_doc.full_text.strip():
            # 提取成功，更新文档
            doc['full_text'] = new_doc.full_text
            doc['pages'] = [p.__dict__ for p in new_doc.pages]
            doc['metadata'] = new_doc.metadata
            fixed_count += 1

            # 统计处理方式
            if file_type == '.pdf' and len(new_doc.full_text) >= 50:
                # 判断是否是直接提取（通常直接提取的文字会更规整）
                if '扫码' not in new_doc.full_text[:100]:  # 简单判断
                    pdf_direct_count += 1
                else:
                    pdf_ocr_count += 1
            elif file_type == '.pdf':
                pdf_ocr_count += 1
            else:
                img_ocr_count += 1
        else:
            still_empty += 1

    # 保存更新后的结果
    logger.info("\n" + "=" * 50)
    logger.info("处理完成统计:")
    logger.info(f"  成功修复: {fixed_count}/{len(empty_files)}")
    logger.info(f"    - PDF直接提取: {pdf_direct_count}")
    logger.info(f"    - PDF OCR: {pdf_ocr_count}")
    logger.info(f"    - 图片OCR: {img_ocr_count}")
    logger.info(f"  仍为空: {still_empty}")
    logger.info(f"  出错: {error_count}")
    logger.info("=" * 50)

    with open(input_path, 'w', encoding='utf-8') as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)

    logger.info(f"结果已更新到: {input_path}")

    # 如果修复了文件，提示需要重新运行后续步骤
    if fixed_count > 0:
        logger.info("\n" + "!" * 50)
        logger.info("注意：由于修复了文件，需要重新运行:")
        logger.info("  3. python scripts/03_parse_qa.py")
        logger.info("  4. python scripts/04_add_metadata.py")
        logger.info("  5. python scripts/05_quality_check.py")
        logger.info("  6. python scripts/06_build_index.py")
        logger.info("!" * 50)


if __name__ == "__main__":
    main()
