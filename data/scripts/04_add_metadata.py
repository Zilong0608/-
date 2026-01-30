# -*- coding: utf-8 -*-
"""
步骤4: 添加Metadata
为chunks添加岗位、难度、问题类型、关键词等标签
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
from src.metadata import MetadataLabeler, KeywordExtractor


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="add_metadata",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("步骤4: 添加Metadata")
    logger.info("=" * 50)

    # 加载chunks
    input_path = config.paths.data_chunks / "chunks.json"
    if not input_path.exists():
        logger.error("请先运行 03_parse_qa.py 解析Q&A")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)

    # 转换为Chunk对象
    chunks = [Chunk.from_dict(d) for d in chunks_data]
    logger.info(f"加载了 {len(chunks)} 个chunks")

    # 创建标注器
    labeler = MetadataLabeler(config.metadata)
    keyword_extractor = KeywordExtractor()

    # 标注
    logger.info("正在添加标签...")
    chunks = labeler.label_chunks(chunks)

    logger.info("正在提取关键词...")
    chunks = keyword_extractor.label_chunks_with_keywords(chunks)

    # 获取统计信息
    stats = labeler.get_statistics(chunks)

    # 打印统计
    logger.info("\n" + "=" * 50)
    logger.info("标注统计")
    logger.info("=" * 50)

    logger.info("\n按内容分类统计:")
    for cat, count in sorted(stats['by_content_category'].items(), key=lambda x: -x[1]):
        logger.info(f"  {cat}: {count}")

    logger.info("\n按岗位统计:")
    for pos, count in sorted(stats['by_position'].items(), key=lambda x: -x[1]):
        logger.info(f"  {pos}: {count}")

    logger.info("\n按难度统计:")
    for diff, count in sorted(stats['by_difficulty'].items(), key=lambda x: -x[1]):
        logger.info(f"  {diff}: {count}")

    logger.info("\n按问题类型统计:")
    for qtype, count in sorted(stats['by_question_type'].items(), key=lambda x: -x[1]):
        logger.info(f"  {qtype}: {count}")

    # 保存结果
    output_path = config.paths.data_chunks / "chunks_with_metadata.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([c.to_dict() for c in chunks], f, ensure_ascii=False, indent=2)

    logger.info(f"\n结果已保存到: {output_path}")

    return chunks


if __name__ == "__main__":
    main()
