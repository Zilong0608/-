# -*- coding: utf-8 -*-
"""
合并二次处理的结果到主数据库
更新 extracted_documents.json 和 chunks.json
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.parsers import QAParser


def main():
    config = get_config()

    logger = setup_logger(
        name="merge_processed_files",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("合并二次处理的结果")
    logger.info("=" * 50)

    # 检查处理结果
    failed_dir = config.paths.data_raw / "需要二次处理"
    results_path = failed_dir / "processing_results.json"

    if not results_path.exists():
        logger.error("找不到处理结果，请先运行 02_process_failed_files.py")
        return

    with open(results_path, 'r', encoding='utf-8') as f:
        processed_results = json.load(f)

    # 筛选成功的结果
    success_results = [r for r in processed_results if r.get('success')]
    logger.info(f"二次处理成功: {len(success_results)} 个文件")

    if len(success_results) == 0:
        logger.info("没有成功提取的文件，无需合并")
        return

    # 1. 更新 extracted_documents.json
    logger.info("\n步骤 1：更新 extracted_documents.json")
    docs_path = config.paths.data_ingest / "extracted_documents.json"

    with open(docs_path, 'r', encoding='utf-8') as f:
        all_docs = json.load(f)

    updated_count = 0
    for result in success_results:
        original_path = result['original_path']

        # 找到对应的文档并更新
        for doc in all_docs:
            if doc['source_path'] == original_path:
                doc['full_text'] = result['full_text']
                doc['pages'] = result['pages']
                doc['metadata'] = result['metadata']
                updated_count += 1
                break

    # 保存更新后的文档
    with open(docs_path, 'w', encoding='utf-8') as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)

    logger.info(f"  更新了 {updated_count} 个文档")

    # 2. 重新生成 chunks
    logger.info("\n步骤 2：为新文档生成 chunks")

    # 创建解析器（传递整个 ChunkerConfig 对象）
    parser = QAParser(config=config.chunker)

    new_chunks = []
    for result in success_results:
        try:
            # 构造文档对象
            doc_dict = {
                'source_path': result['original_path'],
                'full_text': result['full_text'],
                'file_type': result['file_type']
            }

            # 解析QA对
            qa_pairs = parser.parse(result['full_text'])

            # 生成chunks
            if qa_pairs:
                chunks = parser.create_chunks(qa_pairs, doc_dict)
                new_chunks.extend(chunks)
            else:
                # 如果没有QA对，创建文本块
                text_chunks = parser.chunk_long_text(result['full_text'])
                for chunk_text in text_chunks:
                    chunk = {
                        'chunk_id': f"{Path(result['original_path']).stem}_text_{len(new_chunks)}",
                        'chunk_type': 'text',
                        'content': chunk_text,
                        'source_file': result['original_path'],
                        'metadata': result.get('metadata', {})
                    }
                    new_chunks.append(chunk)

        except Exception as e:
            logger.warning(f"生成chunks失败 {result['file_name']}: {e}")

    logger.info(f"  生成了 {len(new_chunks)} 个新 chunks")

    # 3. 合并到现有chunks
    logger.info("\n步骤 3：合并到 chunks.json")
    chunks_path = config.paths.data_chunks / "chunks.json"

    if chunks_path.exists():
        with open(chunks_path, 'r', encoding='utf-8') as f:
            existing_chunks = json.load(f)
    else:
        existing_chunks = []

    # 合并
    total_chunks = existing_chunks + new_chunks

    # 保存
    with open(chunks_path, 'w', encoding='utf-8') as f:
        json.dump(total_chunks, f, ensure_ascii=False, indent=2)

    logger.info(f"  原有chunks: {len(existing_chunks)}")
    logger.info(f"  新增chunks: {len(new_chunks)}")
    logger.info(f"  总chunks: {len(total_chunks)}")

    logger.info("\n" + "=" * 50)
    logger.info("合并完成！")
    logger.info("=" * 50)
    logger.info("\n下一步：运行以下脚本更新索引")
    logger.info("  4. python scripts/04_add_metadata.py")
    logger.info("  5. python scripts/05_quality_check.py")
    logger.info("  6. python scripts/06_build_index.py")


if __name__ == "__main__":
    main()
