# -*- coding: utf-8 -*-
"""
CLI 面试工具
"""

import os
import tempfile
from datetime import datetime
import uuid
import yaml
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown
from rich import box
from dotenv import load_dotenv

from ..core.interview_engine import InterviewEngine
from ..core.personality_manager import PersonalityManager
from ..core.evaluation_engine import EvaluationEngine
from ..services.question_service import QuestionRepository, JsonQuestionRepository
from ..services.data_service import DataService
from ..services.ai_service import AIService
from ..models import DifficultyLevel
from ..utils.logger import setup_logger, get_logger

# 加载环境变量
load_dotenv()

console = Console()
logger = None


class InterviewCLI:
    """
    命令行面试工具
    """

    def __init__(self, engine: InterviewEngine):
        """
        初始化

        Args:
            engine: 面试引擎实例
        """
        self.engine = engine
        self.session_id: Optional[str] = None
        self.is_answering_followup = False
        self._init_tts()

    def _init_tts(self):
        """初始化 TTS 配置"""
        enabled = os.getenv("TTS_ENABLED", "0").strip().lower()
        self.tts_enabled = enabled in {"1", "true", "yes", "y"}
        self.tts_model = os.getenv("TTS_MODEL", "gpt-4o-mini-tts").strip()
        self.tts_voice = os.getenv("TTS_VOICE", "alloy").strip()
        self.tts_format = os.getenv("TTS_FORMAT", "wav").strip().lower()
        self.tts_play = os.getenv("TTS_PLAY", "1").strip().lower() in {"1", "true", "yes", "y"}
        self.tts_output_dir = os.getenv("TTS_OUTPUT_DIR", "").strip()
        max_chars = os.getenv("TTS_MAX_CHARS", "600").strip()
        speed = os.getenv("TTS_SPEED", "").strip()
        try:
            self.tts_max_chars = int(max_chars)
        except ValueError:
            self.tts_max_chars = 600
        try:
            self.tts_speed = float(speed) if speed else None
        except ValueError:
            self.tts_speed = None

    def _speak(self, text: str):
        """TTS 播报"""
        if not self.tts_enabled:
            return
        if not text:
            return
        speak_text = text.strip()
        if self.tts_max_chars > 0 and len(speak_text) > self.tts_max_chars:
            speak_text = speak_text[: self.tts_max_chars]

        try:
            audio_bytes = self.engine.ai_service.text_to_speech(
                text=speak_text,
                model=self.tts_model,
                voice=self.tts_voice,
                response_format=self.tts_format,
                speed=self.tts_speed
            )
            if not audio_bytes:
                return
            audio_path = self._write_tts_audio(audio_bytes)
            if self.tts_play and audio_path:
                try:
                    if audio_path.suffix.lower() == ".wav":
                        import winsound
                        winsound.PlaySound(
                            str(audio_path),
                            winsound.SND_FILENAME | winsound.SND_NODEFAULT
                        )
                    else:
                        os.startfile(str(audio_path))
                except Exception as e:
                    if logger:
                        logger.warning(f"TTS playback failed: {e}")
        except Exception as e:
            if logger:
                logger.warning(f"TTS failed: {e}")

    def _write_tts_audio(self, audio_bytes: bytes) -> Optional[Path]:
        """写入 TTS 音频文件"""
        extension = self._guess_audio_extension(audio_bytes)
        if self.tts_output_dir:
            output_dir = Path(self.tts_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"tts_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{extension}"
            path = output_dir / file_name
            path.write_bytes(audio_bytes)
            return path

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
        temp_file.write(audio_bytes)
        temp_file.flush()
        temp_file.close()
        return Path(temp_file.name)

    def _guess_audio_extension(self, audio_bytes: bytes) -> str:
        """根据返回内容猜测音频后缀"""
        if self.tts_format == "wav":
            if len(audio_bytes) >= 12 and audio_bytes[0:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
                return ".wav"
        return ".mp3"

    def run(self):
        """运行 CLI 面试"""
        try:
            self._show_welcome()

            # 配置面试参数
            config = self._configure_interview()
            if not config:
                return

            # 创建会话
            session = self.engine.create_session(**config)
            self.session_id = session.session_id

            console.print(f"\n[green]✓ 面试会话已创建: {self.session_id}[/green]\n")

            # 启动面试
            opening, first_question = self.engine.start_interview(self.session_id)

            # 显示开场白
            self._show_opening(opening, session.personality.name)

            # 显示第一题
            self._show_question(first_question, 1)

            # 开始答题循环
            self._interview_loop()

            # 结束面试
            self._end_interview()

        except KeyboardInterrupt:
            console.print("\n\n[yellow]面试已中断[/yellow]")
            if self.session_id and Confirm.ask("是否保存当前进度并生成报告？"):
                self._end_interview()
        except Exception as e:
            console.print(f"\n[red]错误: {e}[/red]")
            logger.error(f"CLI error: {e}", exc_info=True)

    def _show_welcome(self):
        """显示欢迎界面"""
        welcome_text = """
# 🎯 AI 面试官系统

欢迎使用智能面试系统！

本系统特点：
- 📚 基于 RAG 的海量题库
- 🎭 多种面试官人格
- 📊 多维度答案评估
- 💡 智能追问机制
- 📈 详细面试报告
        """

        console.print(Panel(
            Markdown(welcome_text),
            title="欢迎",
            border_style="cyan",
            box=box.DOUBLE
        ))

    def _configure_interview(self) -> Optional[dict]:
        """
        配置面试参数

        Returns:
            配置字典，如果用户取消则返回None
        """
        console.print("\n[bold cyan]面试配置[/bold cyan]\n")

        # 选择岗位类型
        job_type = Prompt.ask(
            "请输入岗位类型",
            default="后端开发"
        )

        # 选择难度
        difficulty_map = {
            "1": DifficultyLevel.BASIC,
            "2": DifficultyLevel.INTERMEDIATE,
            "3": DifficultyLevel.ADVANCED
        }
        console.print("\n难度级别:")
        console.print("  1. 简单 (easy)")
        console.print("  2. 中等 (medium)")
        console.print("  3. 困难 (hard)")

        difficulty_choice = Prompt.ask(
            "请选择难度",
            choices=["1", "2", "3"],
            default="2"
        )
        difficulty = difficulty_map[difficulty_choice]

        # 题目数量
        max_questions = int(Prompt.ask(
            "题目数量",
            default="10"
        ))

        # 选择人格
        personalities = self.engine.personality_manager.get_all_personality_names()
        console.print("\n可用面试官人格:")
        for i, name in enumerate(personalities, 1):
            personality = self.engine.personality_manager.get_personality_by_name(name)
            console.print(f"  {i}. {name} - {personality.description}")

        console.print(f"  0. 随机选择")

        personality_choice = Prompt.ask(
            "请选择面试官人格",
            choices=[str(i) for i in range(len(personalities) + 1)],
            default="0"
        )

        personality_name = None
        if personality_choice != "0":
            personality_name = personalities[int(personality_choice) - 1]

        return {
            "job_type": job_type,
            "difficulty": difficulty,
            "max_questions": max_questions,
            "personality_name": personality_name
        }

    def _show_opening(self, opening: str, personality_name: str):
        """显示开场白"""
        console.print(Panel(
            opening,
            title=f"面试官: {personality_name}",
            border_style="blue",
            box=box.ROUNDED
        ))
        self._speak(opening)

    def _show_question(self, question: str, question_num: int):
        """显示问题"""
        console.print(f"\n[bold yellow]问题 {question_num}:[/bold yellow]")
        console.print(Panel(
            question,
            border_style="yellow",
            box=box.ROUNDED
        ))
        self._speak(question)

    def _get_answer(self) -> str:
        """获取用户答案"""
        console.print("\n[cyan]请输入您的答案（输入 'skip' 跳过此题）:[/cyan]")
        lines = []

        while True:
            line = input()
            if line.strip().lower() == 'skip':
                return 'skip'
            if not line and lines:  # 空行且已有内容，结束输入
                break
            if line:
                lines.append(line)

        return "\n".join(lines)

    def _show_evaluation(self, result: dict):
        """显示评估结果"""
        eval_data = result['evaluation']

        # 创建评分表格
        table = Table(title="评估结果", box=box.ROUNDED, border_style="green")
        table.add_column("维度", style="cyan")
        table.add_column("得分", style="yellow", justify="right")

        table.add_row("技术准确性", f"{eval_data['technical_accuracy']:.1f}/10")
        table.add_row("表达清晰度", f"{eval_data['clarity']:.1f}/10")
        table.add_row("深度广度", f"{eval_data['depth_breadth']:.1f}/10")
        table.add_row("关键词覆盖", f"{eval_data['keyword_coverage']:.0%}")
        table.add_row("[bold]总分[/bold]", f"[bold]{eval_data['total_score']:.1f}/10[/bold]")

        console.print("\n")
        console.print(table)

        # 显示反馈
        console.print(f"\n[blue]{result['feedback']}[/blue]")

        # 显示不足和建议
        if eval_data.get('weaknesses'):
            console.print("\n[yellow]主要不足:[/yellow]")
            for weakness in eval_data['weaknesses']:
                console.print(f"  • {weakness}")

        if eval_data.get('suggestions'):
            console.print("\n[green]改进建议:[/green]")
            for suggestion in eval_data['suggestions']:
                console.print(f"  • {suggestion}")

    def _interview_loop(self):
        """答题循环"""
        question_num = 1

        while True:
            # 获取用户答案
            answer = self._get_answer()

            if answer == 'skip':
                console.print("[yellow]已跳过此题[/yellow]")
                # 获取下一题
                next_q = self.engine.get_next_question(self.session_id)
                if not next_q:
                    break
                question_num += 1
                self._show_question(next_q, question_num)
                continue

            # 提交答案
            if self.is_answering_followup:
                # 提交追问答案
                result = self.engine.submit_followup_answer(self.session_id, answer)
                console.print(f"\n[green]{result['feedback']}[/green]")
                self.is_answering_followup = False

                # 获取下一题
                next_q = self.engine.get_next_question(self.session_id)
                if not next_q:
                    break
                question_num += 1
                self._show_question(next_q, question_num)

            else:
                # 提交主问题答案
                result = self.engine.submit_answer(self.session_id, answer)

                # 显示评估结果
                self._show_evaluation(result)

                # 检查是否有追问
                if result['has_followup']:
                    console.print("\n[bold magenta]追问:[/bold magenta]")
                    console.print(Panel(
                        result['followup_question'],
                        border_style="magenta",
                        box=box.ROUNDED
                    ))
                    self._speak(result['followup_question'])
                    self.is_answering_followup = True
                else:
                    # 获取下一题
                    next_q = self.engine.get_next_question(self.session_id)
                    if not next_q:
                        break
                    question_num += 1
                    self._show_question(next_q, question_num)

    def _end_interview(self):
        """结束面试并显示报告"""
        console.print("\n[cyan]正在生成面试报告...[/cyan]")

        report = self.engine.end_interview(self.session_id)

        # 显示报告
        self._show_report(report)

    def _show_report(self, report):
        """显示面试报告"""
        console.print("\n")
        console.print("=" * 60)
        console.print(Panel(
            "[bold cyan]面试报告[/bold cyan]",
            box=box.DOUBLE,
            border_style="cyan"
        ))

        # 总体评分
        score_table = Table(title="总体评分", box=box.ROUNDED, border_style="cyan")
        score_table.add_column("指标", style="cyan")
        score_table.add_column("分数", style="yellow", justify="right")

        score_table.add_row("综合得分", f"{report.overall_score:.1f}/10")
        score_table.add_row("技术准确性", f"{report.avg_technical_accuracy:.1f}/10")
        score_table.add_row("表达清晰度", f"{report.avg_clarity:.1f}/10")
        score_table.add_row("深度广度", f"{report.avg_depth_breadth:.1f}/10")
        score_table.add_row("通过率", f"{report.correct_rate:.0%}")

        console.print(score_table)

        # 薄弱领域
        if report.weak_areas:
            console.print("\n[bold red]薄弱领域:[/bold red]")
            for area in report.weak_areas:
                console.print(f"  • {area}")

        # 优势领域
        if report.strong_areas:
            console.print("\n[bold green]优势领域:[/bold green]")
            for area in report.strong_areas:
                console.print(f"  • {area}")

        # 改进建议
        if report.suggestions:
            console.print("\n[bold blue]改进建议:[/bold blue]")
            for suggestion in report.suggestions:
                console.print(f"  • {suggestion}")

        console.print("\n" + "=" * 60)
        console.print(f"\n[green]感谢您的参与！会话ID: {self.session_id}[/green]\n")


def initialize_engine() -> InterviewEngine:
    """
    初始化面试引擎

    Returns:
        InterviewEngine 实例
    """
    global logger

    # 加载配置
    config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 初始化日志
    log_config = config.get('logging', {})
    logger = setup_logger(
        log_file=log_config.get('file'),
        log_level=log_config.get('level', 'INFO')
    )

    # 初始化组件
    ai_config = config['ai']
    ai_service = AIService(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=ai_config['model'],
        max_retries=ai_config['max_retries'],
        timeout=ai_config['timeout']
    )

    rag_config = config['rag']
    json_path = os.getenv('QUESTION_JSON_PATH')
    if json_path:
        question_repo = JsonQuestionRepository(
            json_path=json_path,
            preload_count=rag_config['preload_count'],
            refill_threshold=rag_config['refill_threshold']
        )
    else:
        question_repo = QuestionRepository(
            vector_store_path=os.getenv('RAG_VECTOR_STORE_PATH', '../数据/data_index'),
            preload_count=rag_config['preload_count'],
            refill_threshold=rag_config['refill_threshold']
        )

    db_path = os.getenv('SQLITE_DB_PATH', '../data/interviews.db')
    data_service = DataService(db_path=db_path)

    personalities_dir = Path(__file__).parent.parent / "config" / "personalities"
    personality_manager = PersonalityManager(str(personalities_dir))

    interview_config = config['interview']
    followup_config = interview_config.get('followup', {})
    score_threshold = followup_config.get('score_threshold')
    if isinstance(score_threshold, (list, tuple)) and len(score_threshold) == 2:
        followup_score_threshold = (float(score_threshold[0]), float(score_threshold[1]))
    else:
        followup_score_threshold = (
            float(interview_config.get('followup_score_min', 6.0)),
            float(interview_config.get('followup_score_max', 8.0))
        )
    evaluation_engine = EvaluationEngine(
        ai_service=ai_service,
        personality_manager=personality_manager,
        followup_score_threshold=followup_score_threshold
    )

    engine = InterviewEngine(
        question_repo=question_repo,
        data_service=data_service,
        personality_manager=personality_manager,
        evaluation_engine=evaluation_engine,
        ai_service=ai_service
    )

    return engine


def main():
    """主函数"""
    try:
        console.print("[cyan]正在初始化面试系统...[/cyan]")
        engine = initialize_engine()
        console.print("[green]✓ 系统初始化完成[/green]\n")

        # 运行 CLI
        cli = InterviewCLI(engine)
        cli.run()

    except Exception as e:
        console.print(f"\n[red]系统错误: {e}[/red]")
        if logger:
            logger.error(f"System error: {e}", exc_info=True)


if __name__ == "__main__":
    main()

