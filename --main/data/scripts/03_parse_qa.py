# -*- coding: utf-8 -*-
"""
步骤3: 解析Q&A并分块
将提取的文本解析为Q&A对，并切分为适合向量检索的chunks
"""

import sys
import json
from pathlib import Path
from typing import List

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import setup_logger
from src.parsers import QAParser, Chunker
from src.extractors.base import ExtractedDocument


def main():
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="parse_qa",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("步骤3: 解析Q&A并分块")
    logger.info("=" * 50)

    # 加载提取结果
    input_path = config.paths.data_ingest / "extracted_documents.json"
    if not input_path.exists():
        logger.error("请先运行 02_extract_text.py 提取文本")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        extracted_docs = json.load(f)

    logger.info(f"加载了 {len(extracted_docs)} 个文档")

    # 创建解析器和分块器
    qa_parser = QAParser(config.chunker)
    chunker = Chunker(config.chunker)

    # 统计
    total_qa_pairs = 0
    total_chunks = 0
    all_chunks = []

    # 处理每个文档
    for i, doc_dict in enumerate(extracted_docs):
        file_name = doc_dict['file_name']
        full_text = doc_dict.get('full_text', '')
        markdown_text = doc_dict.get('markdown_text', '')
        content_text = markdown_text or full_text
        category = doc_dict.get('category', '未分类')
        source_path = doc_dict.get('source_path', '')
        is_question_bank = (category == '\u9898\u5e93') or ('\\\u9898\u5e93\\' in source_path) or ('/\u9898\u5e93/' in source_path)

        if not content_text or not content_text.strip():
            logger.warning(f"[{i+1}] 跳过空文档: {file_name}")
            continue

        logger.info(f"[{i+1}/{len(extracted_docs)}] 处理: {file_name}")

        # 解析Q&A
        qa_pairs = qa_parser.parse(
            text=content_text,
            source_file=doc_dict['source_path'],
            page_num=None
        )

        if is_question_bank:
            heading_qas = qa_parser.parse_headings(
                text=content_text,
                source_file=doc_dict['source_path'],
                page_num=None
            )
            if qa_pairs:
                filtered_headings = []
                for heading_qa in heading_qas:
                    inside_explicit = False
                    for qa in qa_pairs:
                        if qa.start_pos <= heading_qa.start_pos and heading_qa.end_pos <= qa.end_pos:
                            inside_explicit = True
                            break
                    if not inside_explicit:
                        filtered_headings.append(heading_qa)
                if filtered_headings:
                    qa_pairs = sorted(qa_pairs + filtered_headings, key=lambda qa: qa.start_pos)
            else:
                qa_pairs = heading_qas

        if qa_pairs:
            min_answer_len = config.quality.min_content_length
            if is_question_bank:
                qa_pairs = [qa for qa in qa_pairs if qa.answer and len(qa.answer.strip()) >= min_answer_len]
                if not qa_pairs:
                    logger.info("  Question bank has no valid answers; skipped")
                    continue
            logger.info(f"  Parsed {len(qa_pairs)} Q&A pairs")
            total_qa_pairs += len(qa_pairs)

            if not is_question_bank:
                # Merge short Q&A for non-question-bank docs.
                qa_pairs = qa_parser.merge_short_qas(qa_pairs, min_length=50)

            # Convert to chunks.
            chunks = chunker.chunk_qa_pairs(qa_pairs, source_file=doc_dict['source_path'])
        else:
            if is_question_bank:
                logger.info("  Question bank has no Q&A structure; skipped")
                continue
            if markdown_text:
                logger.info("  No Q&A structure; chunking Markdown")
                chunks = chunker.chunk_markdown(
                    text=markdown_text,
                    source_file=doc_dict['source_path']
                )
            else:
                logger.info("  No Q&A structure; chunking plain text")
                chunks = chunker.chunk_plain_text(
                    text=full_text,
                    source_file=doc_dict['source_path']
                )


        for chunk in chunks:
            chunk.metadata['category'] = category

        logger.info(f"  生成 {len(chunks)} 个chunks")
        total_chunks += len(chunks)
        all_chunks.extend([c.to_dict() for c in chunks])

    # 保存chunks
    output_dir = config.paths.data_chunks
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "chunks.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    # 打印统计
    logger.info("\n" + "=" * 50)
    logger.info("解析完成统计")
    logger.info("=" * 50)
    logger.info(f"处理文档数: {len(extracted_docs)}")
    logger.info(f"总Q&A对数: {total_qa_pairs}")
    logger.info(f"总chunks数: {total_chunks}")
    logger.info(f"\n结果已保存到: {output_path}")

    return all_chunks


if __name__ == "__main__":
    main()
