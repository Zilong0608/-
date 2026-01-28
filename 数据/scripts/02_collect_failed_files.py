# -*- coding: utf-8 -*-
"""
收集提取失败的文件，复制到专门的文件夹
"""

import json
import shutil
from pathlib import Path
import sys

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger


def main():
    config = get_config()
    logger = setup_logger(
        name="collect_failed_files",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("收集提取失败的文件")
    logger.info("=" * 50)

    # 加载提取结果
    input_path = config.paths.data_ingest / "extracted_documents.json"
    if not input_path.exists():
        logger.error("找不到 extracted_documents.json")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        all_docs = json.load(f)

    # 找出仍然为空的文件
    empty_files = []
    for doc in all_docs:
        file_type = doc.get('file_type', '')
        # 只处理PDF和图片
        if file_type in ['.pdf', '.jpg', '.jpeg', '.png', '.bmp']:
            if not doc.get('error') and (not doc.get('full_text') or not doc.get('full_text').strip()):
                empty_files.append(doc)

    logger.info(f"找到 {len(empty_files)} 个提取失败的文件")

    if len(empty_files) == 0:
        logger.info("没有需要二次处理的文件")
        return

    # 创建目标文件夹
    target_dir = config.paths.data_raw / "需要二次处理"
    target_dir.mkdir(parents=True, exist_ok=True)

    # 保存文件列表（用于后续处理）
    failed_list_path = target_dir / "failed_files_list.json"

    # 复制文件
    copied_count = 0
    failed_count = 0
    file_list = []

    for doc in empty_files:
        source_path = Path(doc['source_path'])

        if not source_path.exists():
            logger.warning(f"文件不存在: {source_path}")
            failed_count += 1
            continue

        try:
            # 创建目标文件名（保留原始文件名）
            target_path = target_dir / source_path.name

            # 如果文件名重复，添加序号
            counter = 1
            original_stem = target_path.stem
            while target_path.exists():
                target_path = target_dir / f"{original_stem}_{counter}{target_path.suffix}"
                counter += 1

            # 复制文件
            shutil.copy2(source_path, target_path)
            copied_count += 1

            # 记录文件信息
            file_list.append({
                'original_path': str(source_path),
                'new_path': str(target_path),
                'file_type': doc.get('file_type'),
                'file_name': source_path.name
            })

            logger.debug(f"复制: {source_path.name}")

        except Exception as e:
            logger.error(f"复制失败 {source_path.name}: {e}")
            failed_count += 1

    # 保存文件列表
    with open(failed_list_path, 'w', encoding='utf-8') as f:
        json.dump(file_list, f, ensure_ascii=False, indent=2)

    logger.info("\n" + "=" * 50)
    logger.info("收集完成统计:")
    logger.info(f"  成功复制: {copied_count}/{len(empty_files)}")
    logger.info(f"  失败: {failed_count}")
    logger.info(f"  目标文件夹: {target_dir}")
    logger.info(f"  文件列表: {failed_list_path}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
