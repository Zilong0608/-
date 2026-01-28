# -*- coding: utf-8 -*-
"""
面试相关数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum

from .question import Question, DifficultyLevel
from .personality import Personality
from .evaluation import AnswerRecord


class InterviewStatus(str, Enum):
    """面试状态"""
    IDLE = "idle"
    PREPARING = "preparing"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class InterviewConfig:
    """面试配置"""
    job_type: str                       # 岗位类型
    difficulty: DifficultyLevel         # 难度等级
    duration_minutes: int               # 面试时长（分钟）
    personality_name: Optional[str] = None  # 指定人格（None=随机）
    question_category: Optional[str] = None  # ???????????????None=?????????
    max_questions: int = 15             # 最多题目数
    enable_followup: bool = True        # 是否启用追问

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "job_type": self.job_type,
            "difficulty": self.difficulty.value if isinstance(self.difficulty, Enum) else self.difficulty,
            "duration_minutes": self.duration_minutes,
            "personality_name": self.personality_name,
            "question_category": self.question_category,
            "max_questions": self.max_questions,
            "enable_followup": self.enable_followup
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewConfig":
        """从字典创建"""
        return cls(
            job_type=data["job_type"],
            difficulty=DifficultyLevel(data["difficulty"]) if isinstance(data["difficulty"], str) else data["difficulty"],
            duration_minutes=data["duration_minutes"],
            personality_name=data.get("personality_name"),
            question_category=data.get("question_category"),
            max_questions=data.get("max_questions", 15),
            enable_followup=data.get("enable_followup", True)
        )


@dataclass
class InterviewSession:
    """面试会话模型"""
    session_id: str
    config: InterviewConfig
    personality: Personality

    status: InterviewStatus = InterviewStatus.IDLE

    # 题库
    preloaded_questions: List[Question] = field(default_factory=list)
    asked_question_ids: List[str] = field(default_factory=list)
    current_question: Optional[Question] = None

    # 答题记录
    answer_records: List[AnswerRecord] = field(default_factory=list)

    # 时间统计
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # 状态追踪
    is_answering_followup: bool = False
    current_question_index: int = 0
    consecutive_correct: int = 0        # 连续答对次数
    consecutive_wrong: int = 0          # 连续答错次数
    current_difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE

    def get_elapsed_minutes(self) -> float:
        """获取已用时间（分钟）"""
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now()
        elapsed = (end - self.start_time).total_seconds() / 60
        return round(elapsed, 2)

    def is_time_exceeded(self) -> bool:
        """是否超时"""
        return self.get_elapsed_minutes() >= self.config.duration_minutes

    def is_max_questions_reached(self) -> bool:
        """是否达到最大题数"""
        return len(self.asked_question_ids) >= self.config.max_questions

    def should_end(self) -> bool:
        """是否应该结束面试"""
        return self.is_time_exceeded() or self.is_max_questions_reached()

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "config": self.config.to_dict(),
            "personality": self.personality.to_dict(),
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "preloaded_questions": [q.to_dict() for q in self.preloaded_questions],
            "asked_question_ids": self.asked_question_ids,
            "current_question": self.current_question.to_dict() if self.current_question else None,
            "answer_records": [r.to_dict() for r in self.answer_records],
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "current_question_index": self.current_question_index,
            "consecutive_correct": self.consecutive_correct,
            "consecutive_wrong": self.consecutive_wrong,
            "current_difficulty": self.current_difficulty.value if isinstance(self.current_difficulty, Enum) else self.current_difficulty
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewSession":
        """从字典创建"""
        return cls(
            session_id=data["session_id"],
            config=InterviewConfig.from_dict(data["config"]),
            personality=Personality.from_dict(data["personality"]),
            status=InterviewStatus(data["status"]) if isinstance(data["status"], str) else data["status"],
            preloaded_questions=[Question.from_dict(q) for q in data.get("preloaded_questions", [])],
            asked_question_ids=data.get("asked_question_ids", []),
            current_question=Question.from_dict(data["current_question"]) if data.get("current_question") else None,
            answer_records=[AnswerRecord.from_dict(r) for r in data.get("answer_records", [])],
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            current_question_index=data.get("current_question_index", 0),
            consecutive_correct=data.get("consecutive_correct", 0),
            consecutive_wrong=data.get("consecutive_wrong", 0),
            current_difficulty=DifficultyLevel(data["current_difficulty"]) if isinstance(data.get("current_difficulty"), str) else data.get("current_difficulty", DifficultyLevel.INTERMEDIATE)
        )
