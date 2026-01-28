# -*- coding: utf-8 -*-
"""
步骤6: 构建向量索引
将chunks转换为向量并建立索引
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
from src.indexer import VectorStore


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="build_index",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("步骤6: 构建向量索引")
    logger.info("=" * 50)

    # 加载chunks
    input_path = config.paths.data_chunks / "chunks_final.json"
    if not input_path.exists():
        logger.error("请先运行 05_quality_check.py 质量检查")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)

    chunks = [Chunk.from_dict(d) for d in chunks_data]
    logger.info(f"加载了 {len(chunks)} 个chunks")

    # 创建向量存储
    index_dir = config.paths.data_index
    vector_store = VectorStore(
        config=config.index,
        persist_dir=index_dir
    )

    # 初始化
    logger.info(f"\n使用向量库: {config.index.vector_store}")
    logger.info(f"Embedding模型: {config.index.embedding_model}")
    vector_store.initialize()

    # 检查是否需要清空重建
    existing_count = vector_store.count()
    if existing_count > 0:
        logger.warning(f"索引中已有 {existing_count} 个文档")
        # 可以选择清空或追加
        # vector_store.clear()
        logger.info("将追加新文档到现有索引")

    # 添加chunks
    logger.info("\n开始构建索引...")
    vector_store.add_chunks(chunks, batch_size=50, show_progress=True)

    # 保存索引
    vector_store.save()

    # 测试检索
    logger.info("\n--- 测试检索 ---")
    test_queries = [
        "什么是Transformer的注意力机制？",
        "SQL注入漏洞如何防御？",
        "如何进行简历筛选？",
    ]

    for query in test_queries:
        logger.info(f"\n查询: {query}")
        results = vector_store.search(query, top_k=3)

        for i, result in enumerate(results):
            logger.info(f"  [{i+1}] 分数: {result.score:.4f}")
            question = result.question or result.content[:50]
            logger.info(f"      问题: {question[:60]}...")

    # 打印统计
    logger.info("\n" + "=" * 50)
    logger.info("索引构建完成")
    logger.info("=" * 50)
    logger.info(f"索引位置: {index_dir}")
    logger.info(f"总文档数: {vector_store.count()}")

    return vector_store


if __name__ == "__main__":
    main()
