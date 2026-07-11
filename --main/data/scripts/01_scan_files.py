# -*- coding: utf-8 -*-
"""
步骤1: 扫描文件
扫描data_raw目录下的所有文件，生成文件清单和统计信息
"""

import sys
from pathlib import Path

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger, FileScanner


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="scan_files",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("步骤1: 扫描文件")
    logger.info("=" * 50)

    # 创建文件扫描器
    ocr_formats = config.extractor.ocr_formats if config.extractor.enable_ocr else []
    scanner = FileScanner(
        root_dir=config.paths.data_raw,
        supported_formats=config.extractor.supported_formats,
        ocr_formats=ocr_formats
    )

    # 执行扫描
    files = scanner.scan()

    # 获取统计信息
    stats = scanner.get_statistics(files)

    # 打印统计信息
    logger.info("\n" + "=" * 50)
    logger.info("扫描结果统计")
    logger.info("=" * 50)
    logger.info(f"总文件数: {stats['total_files']}")
    logger.info(f"总大小: {stats['total_size'] / 1024 / 1024:.2f} MB")
    logger.info(f"面试题文件: {stats['interview_files_count']}")
    logger.info(f"简历模板文件: {stats['templates_count']}")
    logger.info(f"需要OCR: {stats['ocr_needed_count']}")

    logger.info("\n按格式统计:")
    for fmt, info in sorted(stats['by_format'].items(), key=lambda x: -x[1]['count']):
        logger.info(f"  {fmt}: {info['count']} 个, {info['size']/1024/1024:.2f} MB")

    logger.info("\n按分类统计:")
    for category, info in sorted(stats['by_category'].items(), key=lambda x: -x[1]['count']):
        logger.info(
            f"  {category}: {info['count']} 个 "
            f"(模板: {info['templates']})"
        )

    # 保存扫描结果
    output_path = config.paths.data_reports / "scan_result.json"
    scanner.save_scan_result(files, output_path)

    logger.info("\n" + "=" * 50)
    logger.info(f"扫描完成! 结果已保存到: {output_path}")
    logger.info("=" * 50)

    return files, stats


if __name__ == "__main__":
    main()
