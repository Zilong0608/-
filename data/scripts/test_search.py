# -*- coding: utf-8 -*-
"""
测试检索功能
交互式测试向量检索效果
"""

import sys
from pathlib import Path

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.indexer import VectorStore


def main():
    config = get_config()

    logger = setup_logger(
        name="test_search",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    # 加载向量库
    index_dir = config.paths.data_index
    if not index_dir.exists():
        logger.error("索引目录不存在，请先运行 06_build_index.py")
        return

    logger.info("加载向量库...")
    vector_store = VectorStore(
        config=config.index,
        persist_dir=index_dir
    )
    vector_store.initialize()
    logger.info(f"索引加载完成，共 {vector_store.count()} 个文档")

    print("\n" + "=" * 60)
    print("RAG知识库检索测试")
    print("输入问题进行检索，输入 'q' 退出")
    print("=" * 60)

    while True:
        print()
        query = input("请输入问题: ").strip()

        if query.lower() in ['q', 'quit', 'exit']:
            print("退出测试")
            break

        if not query:
            continue

        # 检索
        results = vector_store.search(query, top_k=5)

        if not results:
            print("未找到相关结果")
            continue

        print(f"\n找到 {len(results)} 个相关结果:\n")

        for i, result in enumerate(results, 1):
            print("-" * 50)
            print(f"[{i}] 相似度: {result.score:.4f}")

            if result.question:
                print(f"问题: {result.question}")

            if result.answer:
                # 只显示答案的前200字
                answer = result.answer
                if len(answer) > 200:
                    answer = answer[:200] + "..."
                print(f"答案: {answer}")

            # 显示metadata
            meta = result.metadata
            if meta.get('position'):
                print(f"岗位: {meta.get('position')}")
            if meta.get('difficulty'):
                print(f"难度: {meta.get('difficulty')}")
            if meta.get('keywords'):
                keywords = meta.get('keywords')
                if isinstance(keywords, str):
                    import json
                    keywords = json.loads(keywords)
                print(f"关键词: {', '.join(keywords[:5])}")


if __name__ == "__main__":
    main()
