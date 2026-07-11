# -*- coding: utf-8 -*-
"""
题目数据模型
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class DifficultyLevel(str, Enum):
    """难度等级"""
    BASIC = "基础"
    INTERMEDIATE = "进阶"
    ADVANCED = "高级"


class QuestionType(str, Enum):
    """题目类型"""
    CONCEPT = "概念题"
    PRINCIPLE = "原理题"
    PRACTICAL = "实战题"
    CODE = "编程题"
    SCENARIO = "场景题"
    COMPARISON = "对比题"
    KNOWLEDGE = "知识题"


@dataclass
class Question:
    """题目模型"""
    question_id: str                    # 题目ID（从RAG中获取）
    content: str                        # 题目内容
    reference_answer: str               # 参考答案
    question_type: QuestionType         # 题目类型
    difficulty: DifficultyLevel         # 难度
    keywords: List[str]                 # 关键词列表
    job_category: str                   # 岗位分类
    metadata: Dict[str, Any] = field(default_factory=dict)  # 其他元数据

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "question_id": self.question_id,
            "content": self.content,
            "reference_answer": self.reference_answer,
            "question_type": self.question_type.value if isinstance(self.question_type, Enum) else self.question_type,
            "difficulty": self.difficulty.value if isinstance(self.difficulty, Enum) else self.difficulty,
            "keywords": self.keywords,
            "job_category": self.job_category,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Question":
        """从字典创建"""
        return cls(
            question_id=data["question_id"],
            content=data["content"],
            reference_answer=data["reference_answer"],
            question_type=QuestionType(data["question_type"]) if isinstance(data["question_type"], str) else data["question_type"],
            difficulty=DifficultyLevel(data["difficulty"]) if isinstance(data["difficulty"], str) else data["difficulty"],
            keywords=data["keywords"],
            job_category=data["job_category"],
            metadata=data.get("metadata", {})
        )
