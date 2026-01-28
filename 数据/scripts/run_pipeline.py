# -*- coding: utf-8 -*-
"""
运行完整的RAG处理管线
依次执行所有步骤
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger


def main():
    parser = argparse.ArgumentParser(description='运行RAG处理管线')
    parser.add_argument('--start', type=int, default=1, help='起始步骤 (1-6)')
    parser.add_argument('--end', type=int, default=6, help='结束步骤 (1-6)')
    parser.add_argument('--skip-templates', action='store_true', default=True,
                        help='跳过简历模板文件')

    args = parser.parse_args()

    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="pipeline",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 60)
    logger.info("RAG知识库构建管线")
    logger.info("=" * 60)
    logger.info(f"执行步骤: {args.start} -> {args.end}")

    steps = {
        1: ("扫描文件", "01_scan_files"),
        2: ("提取文本", "02_extract_text"),
        3: ("解析Q&A", "03_parse_qa"),
        4: ("添加Metadata", "04_add_metadata"),
        5: ("质量检查", "05_quality_check"),
        6: ("构建索引", "06_build_index"),
    }

    for step_num in range(args.start, args.end + 1):
        if step_num not in steps:
            continue

        step_name, module_name = steps[step_num]

        logger.info("\n" + "=" * 60)
        logger.info(f"步骤 {step_num}: {step_name}")
        logger.info("=" * 60)

        try:
            # 动态导入并执行
            module = __import__(module_name)
            module.main()
            logger.info(f"步骤 {step_num} 完成 ✓")

        except Exception as e:
            logger.error(f"步骤 {step_num} 失败: {e}")
            import traceback
            traceback.print_exc()
            break

    logger.info("\n" + "=" * 60)
    logger.info("管线执行完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
