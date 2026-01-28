# -*- coding: utf-8 -*-
"""
面试报告数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from .evaluation import AnswerRecord


@dataclass
class InterviewReport:
    """面试报告模型"""
    session_id: str
    job_type: str
    personality_name: str

    # 整体评分
    overall_score: float                # 总分（0-100）

    # 维度统计
    avg_technical_accuracy: float
    avg_clarity: float
    avg_depth_breadth: float
    avg_keyword_coverage: float

    # 答题统计
    total_questions: int
    correct_count: int                  # 正确数（>= 8分）
    partial_correct_count: int          # 部分正确（6-8分）
    incorrect_count: int                # 错误（< 6分）
    correct_rate: float                 # 正确率

    # 时间统计
    total_time_minutes: float
    avg_time_per_question: float

    # 薄弱环节
    weak_areas: List[str]               # 薄弱知识点
    strong_areas: List[str]             # 优势领域

    # 改进建议
    suggestions: List[str]

    # 详细记录
    answer_records: List[AnswerRecord]

    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "job_type": self.job_type,
            "personality_name": self.personality_name,
            "overall_score": self.overall_score,
            "avg_technical_accuracy": self.avg_technical_accuracy,
            "avg_clarity": self.avg_clarity,
            "avg_depth_breadth": self.avg_depth_breadth,
            "avg_keyword_coverage": self.avg_keyword_coverage,
            "total_questions": self.total_questions,
            "correct_count": self.correct_count,
            "partial_correct_count": self.partial_correct_count,
            "incorrect_count": self.incorrect_count,
            "correct_rate": self.correct_rate,
            "total_time_minutes": self.total_time_minutes,
            "avg_time_per_question": self.avg_time_per_question,
            "weak_areas": self.weak_areas,
            "strong_areas": self.strong_areas,
            "suggestions": self.suggestions,
            "answer_records": [r.to_dict() for r in self.answer_records],
            "generated_at": self.generated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewReport":
        """从字典创建"""
        return cls(
            session_id=data["session_id"],
            job_type=data["job_type"],
            personality_name=data["personality_name"],
            overall_score=data["overall_score"],
            avg_technical_accuracy=data["avg_technical_accuracy"],
            avg_clarity=data["avg_clarity"],
            avg_depth_breadth=data["avg_depth_breadth"],
            avg_keyword_coverage=data["avg_keyword_coverage"],
            total_questions=data["total_questions"],
            correct_count=data["correct_count"],
            partial_correct_count=data["partial_correct_count"],
            incorrect_count=data["incorrect_count"],
            correct_rate=data["correct_rate"],
            total_time_minutes=data["total_time_minutes"],
            avg_time_per_question=data["avg_time_per_question"],
            weak_areas=data["weak_areas"],
            strong_areas=data["strong_areas"],
            suggestions=data["suggestions"],
            answer_records=[AnswerRecord.from_dict(r) for r in data["answer_records"]],
            generated_at=datetime.fromisoformat(data["generated_at"]) if isinstance(data.get("generated_at"), str) else data.get("generated_at", datetime.now())
        )


@dataclass
class InterviewSummary:
    """面试历史摘要（列表展示用）"""
    session_id: str
    job_type: str
    personality_name: str
    overall_score: float
    total_questions: int
    correct_rate: float
    duration_minutes: float
    interview_date: datetime

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "job_type": self.job_type,
            "personality_name": self.personality_name,
            "overall_score": self.overall_score,
            "total_questions": self.total_questions,
            "correct_rate": self.correct_rate,
            "duration_minutes": self.duration_minutes,
            "interview_date": self.interview_date.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewSummary":
        """从字典创建"""
        return cls(
            session_id=data["session_id"],
            job_type=data["job_type"],
            personality_name=data["personality_name"],
            overall_score=data["overall_score"],
            total_questions=data["total_questions"],
            correct_rate=data["correct_rate"],
            duration_minutes=data["duration_minutes"],
            interview_date=datetime.fromisoformat(data["interview_date"]) if isinstance(data.get("interview_date"), str) else data.get("interview_date", datetime.now())
        )
