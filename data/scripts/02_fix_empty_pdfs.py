# -*- coding: utf-8 -*-
"""
修复空内容PDF
对提取内容为空的PDF文件强制使用OCR重新提取
"""

import sys
import json
from pathlib import Path
from tqdm import tqdm

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.extractors import OCRExtractor


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="fix_empty_pdfs",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("修复空内容PDF文件")
    logger.info("=" * 50)

    # 加载之前的提取结果
    input_path = config.paths.data_ingest / "extracted_documents.json"
    if not input_path.exists():
        logger.error("请先运行 02_extract_text.py")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        all_docs = json.load(f)

    logger.info(f"加载了 {len(all_docs)} 个文档")

    # 找出空内容的PDF文件
    empty_pdfs = []
    for doc in all_docs:
        if (doc.get('file_type') == '.pdf' and
            not doc.get('error') and
            (not doc.get('full_text') or not doc.get('full_text').strip())):
            empty_pdfs.append(doc)

    logger.info(f"找到 {len(empty_pdfs)} 个空内容PDF文件")

    if len(empty_pdfs) == 0:
        logger.info("没有需要修复的PDF文件")
        return

    # 创建OCR提取器
    ocr_extractor = OCRExtractor(
        engine=config.extractor.ocr_engine,
        lang=config.extractor.ocr_lang
    )

    # 重新提取
    fixed_count = 0
    still_empty = 0

    for doc in tqdm(empty_pdfs, desc="OCR处理"):
        source_path = Path(doc['source_path'])

        if not source_path.exists():
            logger.warning(f"文件不存在: {source_path}")
            continue

        try:
            # 使用OCR重新提取
            new_doc = ocr_extractor.extract_from_pdf_images(source_path)

            if new_doc.full_text and new_doc.full_text.strip():
                # 提取成功，更新文档
                doc['full_text'] = new_doc.full_text
                doc['pages'] = [p.__dict__ for p in new_doc.pages]
                doc['metadata'] = new_doc.metadata
                fixed_count += 1
                logger.info(f"✓ 修复成功: {source_path.name} ({len(new_doc.full_text)} 字符)")
            else:
                still_empty += 1
                logger.warning(f"✗ 仍为空: {source_path.name}")

        except Exception as e:
            logger.error(f"处理失败 {source_path.name}: {e}")
            still_empty += 1

    # 保存更新后的结果
    logger.info("\n" + "=" * 50)
    logger.info(f"修复完成: {fixed_count}/{len(empty_pdfs)}")
    logger.info(f"仍为空: {still_empty}")
    logger.info("=" * 50)

    with open(input_path, 'w', encoding='utf-8') as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)

    logger.info(f"结果已更新到: {input_path}")


if __name__ == "__main__":
    main()
