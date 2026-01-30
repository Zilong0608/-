# -*- coding: utf-8 -*-
"""
步骤2: 提取文本
从各种格式的文件中提取文本内容
"""

import sys
import json
from pathlib import Path
from typing import List

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils import (
    setup_logger,
    FileScanner,
    FileInfo,
    clean_extracted_text,
    is_resume_template,
    text_to_markdown,
)
from src.extractors import ExtractorFactory


def main(skip_templates: bool = True):
    # 获取配置
    config = get_config()

    # 设置日志
    logger = setup_logger(
        name="extract_text",
        log_dir=config.paths.logs_dir,
        console_output=True
    )

    logger.info("=" * 50)
    logger.info("步骤2: 提取文本")
    logger.info("=" * 50)

    # 加载扫描结果
    scan_result_path = config.paths.data_reports / "scan_result.json"
    if not scan_result_path.exists():
        logger.error("请先运行 01_scan_files.py 扫描文件")
        return

    files, stats = FileScanner.load_scan_result(scan_result_path)
    logger.info(f"加载了 {len(files)} 个文件信息")

    # 过滤模板文件
    if skip_templates:
        original_count = len(files)
        files = [f for f in files if not f.is_template]
        logger.info(f"跳过 {original_count - len(files)} 个简历模板文件")

    # 创建提取器工厂
    factory = ExtractorFactory(config.extractor)

    # 确保输出目录存在
    output_dir = config.paths.data_ingest
    output_dir.mkdir(parents=True, exist_ok=True)
    md_dir = config.paths.data_markdown
    md_dir.mkdir(parents=True, exist_ok=True)

    # 统计
    success_count = 0
    error_count = 0
    empty_count = 0
    template_count = 0
    extracted_docs = []

    # 提取文本
    total = len(files)
    for i, file_info in enumerate(files):
        logger.info(f"[{i+1}/{total}] 处理: {file_info.name}")

        try:
            doc = factory.extract(file_info.path)

            if doc.full_text:
                doc.full_text = clean_extracted_text(doc.full_text)

            if doc.has_errors:
                logger.warning(f"  提取有错误: {doc.errors}")
                error_count += 1
                continue

            if doc.is_empty:
                logger.warning("  提取内容为空")
                empty_count += 1
                continue

            if file_info.is_template or is_resume_template(file_info.path, doc.full_text):
                logger.info("  跳过简历模板/无效内容")
                template_count += 1
                continue

            markdown_text = text_to_markdown(doc.full_text)

            success_count += 1
            logger.info(f"  成功: {doc.char_count} 字符, {doc.page_count} 页")

            # 保存提取结果
            doc_dict = doc.to_dict()
            doc_dict['category'] = file_info.category
            doc_dict['is_template'] = False
            doc_dict['markdown_text'] = markdown_text
            extracted_docs.append(doc_dict)

            md_name = f"{file_info.path.stem}.md"
            md_path = md_dir / md_name
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown_text)

        except Exception as e:
            logger.error(f"  处理失败: {e}")
            error_count += 1

    # 保存所有提取结果
    output_path = output_dir / "extracted_documents.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(extracted_docs, f, ensure_ascii=False, indent=2)

    # 打印统计
    logger.info("\n" + "=" * 50)
    logger.info("提取完成统计")
    logger.info("=" * 50)
    logger.info(f"成功: {success_count}")
    logger.info(f"空内容: {empty_count}")
    logger.info(f"简历模板: {template_count}")
    logger.info(f"错误: {error_count}")
    logger.info(f"总计: {total}")
    logger.info(f"\n结果已保存到: {output_path}")
    logger.info(f"Markdown目录: {md_dir}")

    return extracted_docs


if __name__ == "__main__":
    main()



