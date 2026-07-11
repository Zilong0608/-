# -*- coding: utf-8 -*-
"""
评估相关数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .question import Question, QuestionType, DifficultyLevel

@dataclass
class EvaluationResult:
    """评估结果模型"""
    question_id: str
    user_answer: str

    # 多维度评分（0-10）
    technical_accuracy: float           # 技术准确性
    clarity: float                      # 表达清晰度
    depth_breadth: float                # 深度广度

    # 关键词分析
    keywords_hit: List[str]             # 命中的关键词
    keywords_missed: List[str]          # 遗漏的关键词
    keyword_coverage: float             # 关键词覆盖率（0-100%）

    # 综合得分
    total_score: float                  # 综合得分（0-10）

    # 反馈
    weaknesses: List[str]               # 不足之处
    suggestions: List[str]              # 改进建议

    # 决策
    needs_followup: bool                # 是否需要追问
    followup_question: Optional[str] = None  # 追问内容

    evaluation_time: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "question_id": self.question_id,
            "user_answer": self.user_answer,
            "technical_accuracy": self.technical_accuracy,
            "clarity": self.clarity,
            "depth_breadth": self.depth_breadth,
            "keywords_hit": self.keywords_hit,
            "keywords_missed": self.keywords_missed,
            "keyword_coverage": self.keyword_coverage,
            "total_score": self.total_score,
            "weaknesses": self.weaknesses,
            "suggestions": self.suggestions,
            "needs_followup": self.needs_followup,
            "followup_question": self.followup_question,
            "evaluation_time": self.evaluation_time.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationResult":
        """从字典创建"""
        return cls(
            question_id=data["question_id"],
            user_answer=data["user_answer"],
            technical_accuracy=data["technical_accuracy"],
            clarity=data["clarity"],
            depth_breadth=data["depth_breadth"],
            keywords_hit=data["keywords_hit"],
            keywords_missed=data["keywords_missed"],
            keyword_coverage=data["keyword_coverage"],
            total_score=data["total_score"],
            weaknesses=data["weaknesses"],
            suggestions=data["suggestions"],
            needs_followup=data["needs_followup"],
            followup_question=data.get("followup_question"),
            evaluation_time=datetime.fromisoformat(data["evaluation_time"]) if isinstance(data.get("evaluation_time"), str) else data.get("evaluation_time", datetime.now())
        )


@dataclass
class AnswerRecord:
    """答题记录模型"""
    question: Question                  # 题目对象
    user_answer: str                    # 用户答案
    is_followup: bool = False           # 是否是追问
    parent_question_id: Optional[str] = None  # 追问对应主问题
    answer_time: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "question": self.question.to_dict(),
            "user_answer": self.user_answer,
            "is_followup": self.is_followup,
            "parent_question_id": self.parent_question_id,
            "answer_time": self.answer_time.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnswerRecord":
        """从字典创建"""
        question_data = data.get("question")
        if isinstance(question_data, dict):
            question = Question.from_dict(question_data)
        else:
            question = Question(
                question_id=data.get("question_id", ""),
                content=data.get("question_content", ""),
                reference_answer=data.get("reference_answer", ""),
                question_type=QuestionType(
                    data.get("question_type", QuestionType.CONCEPT.value)
                ),
                difficulty=DifficultyLevel(
                    data.get("difficulty", DifficultyLevel.INTERMEDIATE.value)
                ),
                keywords=data.get("keywords", []),
                job_category=data.get("job_category", "通用"),
                metadata=data.get("metadata", {})
            )
        return cls(
            question=question,
            user_answer=data["user_answer"],
            is_followup=data.get("is_followup", False),
            parent_question_id=data.get("parent_question_id"),
            answer_time=datetime.fromisoformat(data["answer_time"]) if isinstance(data.get("answer_time"), str) else data.get("answer_time", datetime.now())
        )
