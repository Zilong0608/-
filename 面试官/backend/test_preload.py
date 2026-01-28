#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试预加载问题功能
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.question_service import QuestionRepository

def main():
    print("\n=== 测试 RAG 预加载问题功能 ===\n")
    print("=" * 60)

    try:
        # 连接 RAG 库
        rag_path = r"C:\Users\15048\Desktop\rag库\数据\data_index"
        print(f"连接到: {rag_path}")

        repo = QuestionRepository(
            vector_store_path=rag_path,
            preload_count=5  # 只加载5个问题测试
        )

        print("[OK] RAG 连接成功\n")

        # 测试预加载问题
        print("开始预加载问题...")
        questions = repo.preload_questions()

        print(f"[OK] 成功加载 {len(questions)} 个问题\n")

        # 显示问题
        print("=" * 60)
        for i, q in enumerate(questions, 1):
            print(f"\n问题 {i}:")
            print(f"  内容: {q.content[:100]}...")
            print(f"  类型: {q.job_category}")
            if q.reference_answer:
                print(f"  答案: {q.reference_answer[:80]}...")

        print("\n" + "=" * 60)
        print("[OK] 测试成功！预加载功能正常工作")

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
