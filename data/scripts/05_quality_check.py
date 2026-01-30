# -*- coding: utf-8 -*-
"""
步骤5: 质量检查
检验chunks质量，去重，生成质量报告
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.parsers import Chunk
from src.quality import QualityValidator, Deduplicator


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="quality_check",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("步骤5: 质量检查")
    logger.info("=" * 50)

    # 加载chunks
    input_path = config.paths.data_chunks / "chunks_with_metadata.json"
    if not input_path.exists():
        logger.error("请先运行 04_add_metadata.py 添加Metadata")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)

    chunks = [Chunk.from_dict(d) for d in chunks_data]
    logger.info(f"加载了 {len(chunks)} 个chunks")

    # 创建校验器和去重器
    validator = QualityValidator(config.quality)
    deduplicator = Deduplicator(config.quality)

    # 1. 质量校验
    logger.info("\n--- 质量校验 ---")
    chunks, validation_results = validator.validate_chunks(chunks, remove_invalid=True)
    logger.info(f"校验后剩余: {len(chunks)} 个chunks")

    # 2. 去重
    logger.info("\n--- 去重处理 ---")
    chunks, duplicates = deduplicator.deduplicate(chunks)
    logger.info(f"去重后剩余: {len(chunks)} 个chunks")

    # 3. 生成质量报告
    logger.info("\n--- 生成报告 ---")
    report_dir = config.paths.data_reports
    report_dir.mkdir(parents=True, exist_ok=True)

    # 质量报告
    validator.generate_report(
        validation_results,
        report_dir / "quality_report.json"
    )

    # 抽样检查
    sample_path = report_dir / "sample_for_review.txt"
    validator.sample_for_review(chunks, output_path=sample_path)

    # 4. 保存最终chunks
    output_path = config.paths.data_chunks / "chunks_final.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([c.to_dict() for c in chunks], f, ensure_ascii=False, indent=2)

    # 打印统计
    logger.info("\n" + "=" * 50)
    logger.info("质量检查完成")
    logger.info("=" * 50)
    logger.info(f"最终chunks数: {len(chunks)}")
    logger.info(f"质量报告: {report_dir / 'quality_report.json'}")
    logger.info(f"抽样检查: {sample_path}")
    logger.info(f"最终数据: {output_path}")

    return chunks


if __name__ == "__main__":
    main()
