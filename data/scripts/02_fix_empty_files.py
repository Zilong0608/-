# -*- coding: utf-8 -*-
"""
修复所有空内容文件
对提取内容为空的PDF、图片强制使用OCR重新提取
"""

import os
# 禁用OneDNN/MKLDNN以避免兼容性问题（必须在import paddle之前）
os.environ['PADDLE_USE_ONEDNN'] = '0'
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
# 禁用GPU（避免CUDA相关问题）
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
from src.extractors import OCRExtractor


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="fix_empty_files",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("修复空内容文件（PDF + 图片）")
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

    # 创建OCR提取器
    ocr_extractor = OCRExtractor(
        engine=config.extractor.ocr_engine,
        lang=config.extractor.ocr_lang
    )

    # 重新提取
    fixed_count = 0
    still_empty = 0
    error_count = 0

    for doc in tqdm(empty_files, desc="OCR处理"):
        source_path = Path(doc['source_path'])

        if not source_path.exists():
            logger.warning(f"文件不存在: {source_path}")
            error_count += 1
            continue

        try:
            file_type = doc.get('file_type')

            # 根据文件类型选择提取方法
            if file_type == '.pdf':
                new_doc = ocr_extractor.extract_from_pdf_images(source_path)
            else:  # 图片
                new_doc = ocr_extractor.extract(source_path)

            if new_doc.full_text and new_doc.full_text.strip():
                # 提取成功，更新文档
                doc['full_text'] = new_doc.full_text
                doc['pages'] = [p.__dict__ for p in new_doc.pages]
                doc['metadata'] = new_doc.metadata
                fixed_count += 1
                logger.debug(f"✓ 修复: {source_path.name} ({len(new_doc.full_text)} 字符)")
            else:
                still_empty += 1
                logger.debug(f"✗ 仍空: {source_path.name}")

        except Exception as e:
            logger.error(f"处理失败 {source_path.name}: {e}")
            error_count += 1

    # 保存更新后的结果
    logger.info("\n" + "=" * 50)
    logger.info("修复完成统计:")
    logger.info(f"  成功修复: {fixed_count}/{len(empty_files)}")
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
