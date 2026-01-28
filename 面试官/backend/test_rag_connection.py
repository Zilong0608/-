#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 RAG 连接
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.table import Table
from rich import box

from app.services.question_service import QuestionRepository

console = Console()


def main():
    console.print("\n[bold cyan]测试 RAG 数据库连接[/bold cyan]\n")

    try:
        # 连接 RAG 库
        rag_path = r"C:\Users\15048\Desktop\rag库\数据\data_index"
        console.print(f"[cyan]连接到: {rag_path}[/cyan]")

        repo = QuestionRepository(
            vector_store_path=rag_path,
            preload_count=10
        )

        # 测试连接
        if not repo.test_connection():
            console.print("[red]✗ RAG 连接失败[/red]")
            return

        console.print(f"[green]✓ RAG 连接成功[/green]")
        console.print(f"[green]✓ 集合名称: {repo.collection.name}[/green]")
        console.print(f"[green]✓ 文档数量: {repo.collection.count()}[/green]\n")

        # 测试预加载问题
        console.print("[cyan]测试预加载问题...[/cyan]")
        questions = repo.preload_questions()

        console.print(f"[green]✓ 成功加载 {len(questions)} 个问题[/green]\n")

        # 显示前5个问题
        if questions:
            table = Table(title="预加载的问题示例", box=box.ROUNDED, show_lines=True)
            table.add_column("序号", style="cyan", width=6)
            table.add_column("问题内容", style="yellow", width=60)
            table.add_column("岗位类型", style="green", width=15)

            for i, q in enumerate(questions[:5], 1):
                content = q.content[:100] + "..." if len(q.content) > 100 else q.content
                table.add_row(str(i), content, q.job_category)

            console.print(table)

        # 测试关键词搜索
        console.print("\n[cyan]测试关键词搜索...[/cyan]")
        test_keywords = ["Python", "算法", "数据库"]

        for keyword in test_keywords:
            results = repo.search_questions_by_keyword(keyword, top_k=3)
            if results:
                console.print(f"[green]✓ '{keyword}' 搜索到 {len(results)} 个相关问题[/green]")
                for i, q in enumerate(results[:2], 1):
                    content = q.content[:80] + "..." if len(q.content) > 80 else q.content
                    console.print(f"    {i}. {content}")
            else:
                console.print(f"[yellow]⊙ '{keyword}' 未搜索到相关问题[/yellow]")

        console.print("\n[bold green]✓ 所有测试通过！[/bold green]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ 测试失败: {e}[/bold red]\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
