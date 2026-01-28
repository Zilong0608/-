# 脚本说明

本目录包含 RAG 数据处理全流程脚本，以及若干修复/辅助工具。

核心流程（常用顺序）
- 00_classify_files.py：原始文件分类，可移动或复制到新目录。
- 01_scan_files.py：扫描输入文件，生成 `data_reports/scan_result.json`。
- 02_extract_text.py：抽取文本，生成 `data_ingest/extracted_documents.json`。
- 03_parse_qa.py：解析 Q&A 并切块，生成 `data_chunks/chunks.json`。
- 04_add_metadata.py：为 chunks 添加岗位、难度、题型、关键词等标签。
- 05_quality_check.py：质量检查与去重，输出质量报告。
- 06_build_index.py：生成向量索引。

LLM 版本
- 03_parse_qa_llm.py：针对单个文件的 LLM 解析与切块，输出 `data_chunks/chunks_llm.json`（支持 raw 兜底输出）。
- 07_merge_dedup_questions_llm.py：合并“第一轮仔细清洗”问题，LLM 清洗/合并/去重并按类别输出。

只导出“问题”
- 04_export_questions.py：从 chunks 文件导出问题文本，输出 `data_reports/questions.json`。
- 04_extract_questions_from_cleaned.py：扫描“清洗后数据”，直接提取问题文本，输出 `data_reports/questions_only.json`。
- 04_extract_questions_llm.py：扫描“清洗后数据/题库”，用 LLM 提取问题，输出 `data_chunks/questions_llm.json`。

抽取失败修复
- 02_collect_failed_files.py：收集抽取失败的文件。
- 02_fix_empty_files.py：对空内容文件强制 OCR 重新抽取。
- 02_fix_empty_files_smart.py：智能 OCR 回退（空内容才启用）。
- 02_fix_empty_files_v3.py：改进版智能 OCR。
- 02_fix_empty_pdfs.py：仅修复空内容 PDF。
- 02_process_failed_files.py：对失败文件用 EasyOCR 重试（较慢）。
- 02_reextract_all_fast.py：快速重抽全量（不做 OCR）。
- 02_merge_processed_files.py：合并二次处理结果到主数据集。

索引维护
- 06_incremental_index.py：仅为新 chunks 增量建索引。

其他
- run_pipeline.py：一键跑完整流程。
- test_search.py：交互式检索测试。
