# -*- coding: utf-8 -*-
"""
快速重新提取所有文档
1. 重新提取所有文档（不管现在有没有内容）
2. 只用直接提取（不用OCR，速度快）
3. 提取失败的 → 复制到"需要二次处理"文件夹
4. 只处理文档类型（PDF、PPT、PPTX、DOC、DOCX）
"""

import os
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
from src.extractors import PDFExtractor, DocExtractor


def main():
    config = get_config()

    logger = setup_logger(
        name="reextract_all_fast",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("快速重新提取所有文档")
    logger.info("=" * 50)

    # 加载所有文档
    input_path = config.paths.data_ingest / "extracted_documents.json"
    if not input_path.exists():
        logger.error("请先运行 01_scan_files.py 和 02_extract_text.py")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        all_docs = json.load(f)

    # 筛选出所有文档类型（不管有没有内容）
    doc_files = []
    for doc in all_docs:
        file_type = doc.get('file_type', '')
        # 只处理文档类型
        if file_type in ['.pdf', '.ppt', '.pptx', '.doc', '.docx']:
            doc_files.append(doc)

    # 统计
    type_counts = {}
    for d in doc_files:
        ft = d.get('file_type', 'unknown')
        type_counts[ft] = type_counts.get(ft, 0) + 1

    logger.info(f"找到 {len(doc_files)} 个文档需要重新提取:")
    for ft, count in sorted(type_counts.items()):
        logger.info(f"  - {ft}: {count}")

    if len(doc_files) == 0:
        logger.info("没有文档需要处理")
        return

    # 创建"需要二次处理"文件夹
    retry_dir = config.paths.data_raw / "需要二次处理"
    retry_dir.mkdir(parents=True, exist_ok=True)

    # 创建提取器
    logger.info("\n初始化提取器（快速模式）...")
    pdf_extractor = PDFExtractor(engine='pymupdf')  # 使用pymupdf，最快
    doc_extractor = DocExtractor()

    # 统计
    success_count = 0
    need_retry_count = 0
    already_ok_count = 0
    error_count = 0

    # 记录需要二次处理的文件
    retry_files = []

    logger.info("\n开始处理...")
    for doc in tqdm(doc_files, desc="快速提取"):
        source_path = Path(doc['source_path'])

        if not source_path.exists():
            logger.warning(f"文件不存在: {source_path}")
            error_count += 1
            continue

        file_type = doc.get('file_type')

        # 如果已经有内容了，跳过（节省时间）
        existing_text = doc.get('full_text', '').strip()
        if existing_text and len(existing_text) >= 100:
            already_ok_count += 1
            continue

        success = False
        new_doc = None

        try:
            # 快速直接提取（不用OCR）
            if file_type == '.pdf':
                try:
                    new_doc = pdf_extractor.extract(source_path)
                    if new_doc.full_text and len(new_doc.full_text.strip()) >= 50:
                        success = True
                        logger.debug(f"✓ PDF提取: {source_path.name}")
                except Exception as e:
                    logger.debug(f"PDF提取失败: {source_path.name}")

            elif file_type in ['.ppt', '.pptx', '.doc', '.docx']:
                try:
                    new_doc = doc_extractor.extract(source_path)
                    if new_doc.full_text and len(new_doc.full_text.strip()) >= 50:
                        success = True
                        logger.debug(f"✓ 文档提取: {source_path.name}")
                except Exception as e:
                    logger.debug(f"文档提取失败: {source_path.name}")

            # 如果成功提取，更新文档
            if success and new_doc:
                doc['full_text'] = new_doc.full_text
                doc['pages'] = [p.__dict__ for p in new_doc.pages]
                doc['metadata'] = new_doc.metadata
                success_count += 1
            else:
                # 提取失败，复制到"需要二次处理"文件夹
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
                    logger.debug(f"→ 待二次处理: {source_path.name}")

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

    # 显示统计
    logger.info("\n" + "=" * 50)
    logger.info("处理完成统计:")
    logger.info(f"  总文档数: {len(doc_files)}")
    logger.info(f"  已有内容（跳过）: {already_ok_count}")
    logger.info(f"  本次成功提取: {success_count}")
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
    if success_count > 0:
        logger.info("\n建议重新运行后续步骤刷新数据:")
        logger.info("  python scripts/03_parse_qa.py")

    if need_retry_count > 0:
        logger.info("\n晚上运行二次处理（使用EasyOCR）:")
        logger.info("  python scripts/02_process_failed_files.py")


if __name__ == "__main__":
    main()
