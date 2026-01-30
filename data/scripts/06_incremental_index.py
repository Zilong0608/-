# -*- coding: utf-8 -*-
"""
增量更新向量索引
只为新增的chunks生成向量并添加到现有索引
速度快，适合小批量更新
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
        name="incremental_index",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("增量更新向量索引")
    logger.info("=" * 50)

    # 加载所有chunks
    input_path = config.paths.data_chunks / "chunks_final.json"
    if not input_path.exists():
        logger.error("请先运行 05_quality_check.py 质量检查")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)

    all_chunks = [Chunk.from_dict(d) for d in chunks_data]
    logger.info(f"加载了 {len(all_chunks)} 个chunks")

    # 创建向量存储
    index_dir = config.paths.data_index
    vector_store = VectorStore(
        config=config.index,
        persist_dir=index_dir
    )

    # 初始化
    logger.info(f"\n使用向量库: {config.index.vector_store}")
    logger.info(f"Embedding模型: {config.index.embedding_model}")

    try:
        vector_store.initialize()
    except Exception as e:
        logger.error(f"初始化向量库失败: {e}")
        logger.error("请确保已经运行过 06_build_index.py 构建初始索引")
        return

    # 检查现有索引
    existing_count = vector_store.count()
    logger.info(f"现有索引文档数: {existing_count}")

    if existing_count == 0:
        logger.warning("索引为空，建议运行 06_build_index.py 构建完整索引")
        logger.info("现在将添加所有chunks...")
        new_chunks = all_chunks
    else:
        # 获取已存在的chunk_id列表
        logger.info("正在检查哪些chunks是新的...")

        if config.index.vector_store == 'chroma':
            # ChromaDB: 获取所有已存在的IDs
            try:
                existing_data = vector_store._store.get(include=[])
                existing_ids = set(existing_data['ids'])
                logger.info(f"现有chunk IDs数量: {len(existing_ids)}")
            except Exception as e:
                logger.warning(f"无法获取现有IDs: {e}")
                logger.warning("将添加所有chunks（可能会有重复）")
                existing_ids = set()
        else:
            # FAISS: 从内存中获取
            existing_ids = set(vector_store._faiss_ids)
            logger.info(f"现有chunk IDs数量: {len(existing_ids)}")

        # 找出新的chunks
        new_chunks = [c for c in all_chunks if c.chunk_id not in existing_ids]
        logger.info(f"发现 {len(new_chunks)} 个新chunks需要添加")

    if len(new_chunks) == 0:
        logger.info("\n没有新chunks需要添加，索引已是最新！")
        logger.info("=" * 50)
        return

    # 添加新chunks
    logger.info(f"\n开始为 {len(new_chunks)} 个新chunks生成向量...")
    logger.info("预计时间：约 {:.1f} 分钟".format(len(new_chunks) / 100))

    vector_store.add_chunks(new_chunks, batch_size=50, show_progress=True)

    # 保存索引
    vector_store.save()

    # 打印统计
    logger.info("\n" + "=" * 50)
    logger.info("增量更新完成")
    logger.info("=" * 50)
    logger.info(f"原有文档数: {existing_count}")
    logger.info(f"新增文档数: {len(new_chunks)}")
    logger.info(f"当前总数: {vector_store.count()}")
    logger.info(f"索引位置: {index_dir}")

    # 测试检索（使用新数据相关的查询）
    logger.info("\n--- 测试检索 ---")
    test_queries = [
        "群面的技巧是什么？",
        "携程笔试题有哪些？",
        "产品经理面试问题",
    ]

    for query in test_queries:
        logger.info(f"\n查询: {query}")
        try:
            results = vector_store.search(query, top_k=3)

            for i, result in enumerate(results):
                logger.info(f"  [{i+1}] 分数: {result.score:.4f}")
                question = result.question or result.content[:50]
                logger.info(f"      问题: {question[:60]}...")
                logger.info(f"      来源: {result.metadata.get('source_file', 'Unknown')[:50]}...")
        except Exception as e:
            logger.error(f"检索失败: {e}")

    logger.info("\n" + "=" * 50)
    logger.info("✓ 索引更新成功！")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
