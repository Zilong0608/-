#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
系统初始化脚本
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv

from app.services.question_service import QuestionRepository
from app.services.ai_service import AIService
from app.services.data_service import DataService

console = Console()


def check_env_file():
    """检查环境变量文件"""
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"

    if not env_file.exists():
        console.print("[yellow]警告: .env 文件不存在[/yellow]")
        if env_example.exists():
            console.print("[cyan]请复制 .env.example 为 .env 并填写配置[/cyan]")
            console.print(f"[cyan]cp {env_example} {env_file}[/cyan]")
        return False

    console.print("[green]✓ .env 文件存在[/green]")
    return True


def check_openai_key():
    """检查 OpenAI API Key"""
    load_dotenv()
    api_key = os.getenv('OPENAI_API_KEY')

    if not api_key or api_key == 'your_openai_api_key_here':
        console.print("[red]✗ OpenAI API Key 未配置[/red]")
        console.print("[yellow]请在 .env 文件中设置 OPENAI_API_KEY[/yellow]")
        return False

    console.print("[green]✓ OpenAI API Key 已配置[/green]")
    return True


def check_rag_connection():
    """检查 RAG 连接"""
    try:
        load_dotenv()
        vector_store_path = os.getenv('RAG_VECTOR_STORE_PATH', '../数据/data_index')

        console.print(f"[cyan]检查 RAG 数据库: {vector_store_path}[/cyan]")

        if not Path(vector_store_path).exists():
            console.print(f"[red]✗ RAG 数据库路径不存在: {vector_store_path}[/red]")
            return False

        repo = QuestionRepository(vector_store_path)

        if repo.test_connection():
            count = repo.collection.count()
            console.print(f"[green]✓ RAG 连接成功，共 {count} 个文档[/green]")
            return True
        else:
            console.print("[red]✗ RAG 连接失败[/red]")
            return False

    except Exception as e:
        console.print(f"[red]✗ RAG 连接错误: {e}[/red]")
        return False


def check_ai_connection():
    """检查 AI 服务连接"""
    try:
        load_dotenv()
        api_key = os.getenv('OPENAI_API_KEY')

        if not api_key or api_key == 'your_openai_api_key_here':
            console.print("[yellow]⊙ 跳过 AI 连接测试（API Key 未配置）[/yellow]")
            return False

        console.print("[cyan]测试 OpenAI API 连接...[/cyan]")

        ai_service = AIService(api_key=api_key, model="gpt-4o")

        if ai_service.test_connection():
            console.print("[green]✓ OpenAI API 连接成功[/green]")
            return True
        else:
            console.print("[red]✗ OpenAI API 连接失败[/red]")
            return False

    except Exception as e:
        console.print(f"[red]✗ AI 连接错误: {e}[/red]")
        return False


def init_database():
    """初始化数据库"""
    try:
        load_dotenv()
        db_path = os.getenv('SQLITE_DB_PATH', '../data/interviews.db')

        console.print(f"[cyan]初始化数据库: {db_path}[/cyan]")

        data_service = DataService(db_path)
        console.print("[green]✓ 数据库初始化成功[/green]")
        return True

    except Exception as e:
        console.print(f"[red]✗ 数据库初始化失败: {e}[/red]")
        return False


def main():
    """主函数"""
    console.print(Panel(
        "[bold cyan]AI 面试官系统 - 初始化检查[/bold cyan]",
        expand=False
    ))

    console.print("\n[bold]开始系统检查...[/bold]\n")

    checks = {
        "环境变量文件": check_env_file(),
        "OpenAI API Key": check_openai_key(),
        "RAG 数据库": check_rag_connection(),
        "OpenAI API 连接": check_ai_connection(),
        "本地数据库": init_database()
    }

    console.print("\n" + "=" * 50)
    console.print("\n[bold]检查结果:[/bold]\n")

    all_passed = True
    for name, passed in checks.items():
        status = "[green]✓[/green]" if passed else "[red]✗[/red]"
        console.print(f"  {status} {name}")
        if not passed and name in ["环境变量文件", "OpenAI API Key", "RAG 数据库"]:
            all_passed = False

    console.print("\n" + "=" * 50 + "\n")

    if all_passed:
        console.print("[bold green]系统初始化完成！可以开始使用。[/bold green]\n")
        console.print("运行面试:")
        console.print("  [cyan]python run_cli.py[/cyan]  # 命令行模式")
        console.print("  [cyan]python run_server.py[/cyan]  # API 服务器模式\n")
    else:
        console.print("[bold yellow]部分检查未通过，请修复后重试。[/bold yellow]\n")
        console.print("查看文档: README.md\n")


if __name__ == "__main__":
    main()
