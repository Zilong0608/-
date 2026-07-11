# -*- coding: utf-8 -*-
"""
智能修复空内容文件 V3
1. 先尝试直接提取文字
2. 直接提取失败 → 尝试OCR
3. OCR也失败 → 复制到"需要二次处理"文件夹（晚上用EasyOCR处理）
4. 只处理文档类型（PDF、PPT、PPTX、DOCX），忽略图片
"""

import os
# 禁用OneDNN/MKLDNN以避免兼容性问题
os.environ['PADDLE_USE_ONEDNN'] = '0'
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

import sys
import json
import shutil
from pathlib import Path
from tqdm import tqdm

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.extractors import OCRExtractor, PDFExtractor, DocExtractor


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="fix_empty_files_v3",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("智能修复空内容文件 V3")
    logger.info("=" * 50)

    # 加载之前的提取结果
    input_path = config.paths.data_ingest / "extracted_documents.json"
    if not input_path.exists():
        logger.error("请先运行 02_extract_text.py")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        all_docs = json.load(f)

    logger.info(f"加载了 {len(all_docs)} 个文档")

    # 找出空内容的文件（只要文档类型，不要图片）
    empty_files = []
    for doc in all_docs:
        file_type = doc.get('file_type', '')
        # 只处理文档类型：PDF、PPT、PPTX、DOCX
        if file_type in ['.pdf', '.ppt', '.pptx', '.docx', '.doc']:
            if not doc.get('error') and (not doc.get('full_text') or not doc.get('full_text').strip()):
                empty_files.append(doc)

    # 统计
    type_counts = {}
    for d in empty_files:
        ft = d.get('file_type', 'unknown')
        type_counts[ft] = type_counts.get(ft, 0) + 1

    logger.info(f"找到 {len(empty_files)} 个空内容文档:")
    for ft, count in sorted(type_counts.items()):
        logger.info(f"  - {ft}: {count}")

    if len(empty_files) == 0:
        logger.info("没有需要修复的文件")
        return

    # 创建"需要二次处理"文件夹
    retry_dir = config.paths.data_raw / "需要二次处理"
    retry_dir.mkdir(parents=True, exist_ok=True)

    # 创建提取器
    logger.info("\n初始化提取器...")
    pdf_extractor = PDFExtractor(engine=config.extractor.pdf_extractor)
    doc_extractor = DocExtractor()

    # 使用PaddleOCR（比EasyOCR快）
    logger.info("使用 PaddleOCR 引擎（快速模式）")
    ocr_extractor = OCRExtractor(
        engine='paddleocr',
        lang='ch'
    )

    # 重新提取
    fixed_count = 0
    need_retry_count = 0
    error_count = 0

    # 记录需要二次处理的文件
    retry_files = []

    logger.info("\n开始处理...")
    for doc in tqdm(empty_files, desc="智能提取"):
        source_path = Path(doc['source_path'])

        if not source_path.exists():
            logger.warning(f"文件不存在: {source_path}")
            error_count += 1
            continue

        file_type = doc.get('file_type')
        success = False
        new_doc = None

        try:
            # 步骤1: 先尝试直接提取文字
            if file_type == '.pdf':
                try:
                    new_doc = pdf_extractor.extract(source_path)
                    if new_doc.full_text and len(new_doc.full_text.strip()) >= 50:
                        success = True
                        logger.debug(f"✓ PDF直接提取: {source_path.name}")
                except Exception as e:
                    logger.debug(f"PDF直接提取失败，尝试OCR: {source_path.name}")

            elif file_type in ['.ppt', '.pptx', '.doc', '.docx']:
                try:
                    new_doc = doc_extractor.extract(source_path)
                    if new_doc.full_text and len(new_doc.full_text.strip()) >= 50:
                        success = True
                        logger.debug(f"✓ 文档直接提取: {source_path.name}")
                except Exception as e:
                    logger.debug(f"文档提取失败: {source_path.name} - {e}")

            # 步骤2: 直接提取失败，尝试OCR（只对PDF）
            if not success and file_type == '.pdf':
                try:
                    new_doc = ocr_extractor.extract_from_pdf_images(source_path)
                    if new_doc and new_doc.full_text and new_doc.full_text.strip():
                        success = True
                        logger.debug(f"✓ PDF OCR成功: {source_path.name}")
                except Exception as e:
                    logger.debug(f"PDF OCR失败: {source_path.name} - {e}")

            # 如果成功提取，更新文档
            if success and new_doc:
                doc['full_text'] = new_doc.full_text
                doc['pages'] = [p.__dict__ for p in new_doc.pages]
                doc['metadata'] = new_doc.metadata
                fixed_count += 1
            else:
                # 步骤3: 提取失败，复制到"需要二次处理"文件夹
                try:
                    target_path = retry_dir / source_path.name

                    # 如果文件名重复，添加序号
                    counter = 1
                    original_stem = target_path.stem
                    while target_path.exists():
                        target_path = retry_dir / f"{original_stem}_{counter}{target_path.suffix}"
                        counter += 1

                    shutil.copy2(source_path, target_path)

                    retry_files.append({
                        'original_path': str(source_path),
                        'new_path': str(target_path),
                        'file_type': file_type,
                        'file_name': source_path.name
                    })

                    need_retry_count += 1
                    logger.debug(f"→ 复制到待处理: {source_path.name}")

                except Exception as e:
                    logger.error(f"复制失败 {source_path.name}: {e}")
                    error_count += 1

        except Exception as e:
            logger.error(f"处理失败 {source_path.name}: {e}")
            error_count += 1

    # 保存需要二次处理的文件列表
    if retry_files:
        retry_list_path = retry_dir / "failed_files_list.json"
        with open(retry_list_path, 'w', encoding='utf-8') as f:
            json.dump(retry_files, f, ensure_ascii=False, indent=2)

    # 保存更新后的结果
    logger.info("\n" + "=" * 50)
    logger.info("修复完成统计:")
    logger.info(f"  成功修复: {fixed_count}/{len(empty_files)}")
    logger.info(f"  需要二次处理: {need_retry_count}")
    logger.info(f"  出错: {error_count}")

    if need_retry_count > 0:
        logger.info(f"\n  已复制到: {retry_dir}")
        logger.info(f"  文件列表: {retry_dir / 'failed_files_list.json'}")

    logger.info("=" * 50)

    # 保存更新后的文档
    with open(input_path, 'w', encoding='utf-8') as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)

    logger.info(f"\n结果已更新到: {input_path}")

    # 提示后续步骤
    if fixed_count > 0:
        logger.info("\n" + "!" * 50)
        logger.info("注意：由于修复了文件，需要重新运行:")
        logger.info("  3. python scripts/03_parse_qa.py")
        logger.info("  4. python scripts/04_add_metadata.py")
        logger.info("  5. python scripts/05_quality_check.py")
        logger.info("  6. python scripts/06_build_index.py")
        logger.info("!" * 50)

    if need_retry_count > 0:
        logger.info("\n" + "!" * 50)
        logger.info("晚上运行二次处理:")
        logger.info("  python scripts/02_process_failed_files.py")
        logger.info("!" * 50)


if __name__ == "__main__":
    main()
