# -*- coding: utf-8 -*-
"""
处理二次提取的失败文件
使用 EasyOCR 引擎，更稳定但速度较慢
适合晚上运行
"""

import os
# 禁用OneDNN以避免兼容性问题
os.environ['PADDLE_USE_ONEDNN'] = '0'
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

import sys
import json
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.extractors import OCRExtractor, PDFExtractor


def main():
    config = get_config()

    logger = setup_logger(
        name="process_failed_files",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("处理二次提取的失败文件")
    logger.info("使用 EasyOCR 引擎（较慢但稳定）")
    logger.info("=" * 50)

    # 检查失败文件列表
    failed_dir = config.paths.data_raw / "需要二次处理"
    failed_list_path = failed_dir / "failed_files_list.json"

    if not failed_list_path.exists():
        logger.error("找不到失败文件列表，请先运行 02_collect_failed_files.py")
        return

    with open(failed_list_path, 'r', encoding='utf-8') as f:
        failed_files = json.load(f)

    logger.info(f"找到 {len(failed_files)} 个待处理文件")

    # 创建提取器
    logger.info("初始化提取器（EasyOCR）...")
    pdf_extractor = PDFExtractor(engine=config.extractor.pdf_extractor)
    ocr_extractor = OCRExtractor(
        engine='easyocr',  # 使用 EasyOCR
        lang='ch'
    )

    # 结果存储
    results = []
    success_count = 0
    still_empty = 0
    error_count = 0

    start_time = datetime.now()

    logger.info("\n开始处理...")
    logger.info("预计时间：根据文件数量，可能需要数小时")
    logger.info("您可以让脚本在后台运行\n")

    for idx, file_info in enumerate(tqdm(failed_files, desc="OCR处理"), 1):
        file_path = Path(file_info['new_path'])
        file_type = file_info['file_type']
        original_path = file_info['original_path']

        if not file_path.exists():
            logger.warning(f"文件不存在: {file_path.name}")
            error_count += 1
            continue

        try:
            new_doc = None

            # 如果是PDF，先尝试直接提取
            if file_type == '.pdf':
                try:
                    doc = pdf_extractor.extract(file_path)
                    if doc.full_text and len(doc.full_text.strip()) >= 50:
                        new_doc = doc
                        logger.debug(f"PDF直接提取成功: {file_path.name}")
                except:
                    pass

            # 如果直接提取失败或文字太少，使用OCR
            if new_doc is None:
                if file_type == '.pdf':
                    new_doc = ocr_extractor.extract_from_pdf_images(file_path)
                else:
                    new_doc = ocr_extractor.extract(file_path)

            if new_doc and new_doc.full_text and new_doc.full_text.strip():
                # 提取成功
                results.append({
                    'original_path': original_path,
                    'file_name': file_path.name,
                    'file_type': file_type,
                    'full_text': new_doc.full_text,
                    'pages': [p.__dict__ for p in new_doc.pages],
                    'metadata': new_doc.metadata,
                    'success': True
                })
                success_count += 1
                logger.debug(f"✓ 成功: {file_path.name} ({len(new_doc.full_text)} 字符)")
            else:
                still_empty += 1
                results.append({
                    'original_path': original_path,
                    'file_name': file_path.name,
                    'file_type': file_type,
                    'full_text': '',
                    'success': False
                })
                logger.debug(f"✗ 仍空: {file_path.name}")

        except Exception as e:
            logger.error(f"处理失败 {file_path.name}: {e}")
            error_count += 1
            results.append({
                'original_path': original_path,
                'file_name': file_path.name,
                'file_type': file_type,
                'error': str(e),
                'success': False
            })

        # 每处理50个文件保存一次（避免丢失）
        if idx % 50 == 0:
            temp_output = failed_dir / f"processing_results_temp.json"
            with open(temp_output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"已处理 {idx}/{len(failed_files)}，临时结果已保存")

    end_time = datetime.now()
    elapsed = end_time - start_time

    # 保存最终结果
    output_path = failed_dir / "processing_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("\n" + "=" * 50)
    logger.info("处理完成统计:")
    logger.info(f"  成功提取: {success_count}/{len(failed_files)}")
    logger.info(f"  仍为空: {still_empty}")
    logger.info(f"  出错: {error_count}")
    logger.info(f"  耗时: {elapsed}")
    logger.info(f"  结果保存到: {output_path}")
    logger.info("=" * 50)

    if success_count > 0:
        logger.info("\n下一步：运行 02_merge_processed_files.py 合并结果到主数据库")


if __name__ == "__main__":
    main()
