# -*- coding: utf-8 -*-
"""
面试官人格数据模型
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Personality:
    """面试官人格模型"""
    name: str                           # 人格名称
    description: str                    # 描述
    traits: Dict[str, int]             # 特征：strictness, friendliness, pressure, patience
    prompts: Dict[str, str]            # 各种场景的文案模板
    evaluation_bias: Dict[str, float] = field(default_factory=dict)  # 评分倾向

    def get_opening(self) -> str:
        """获取开场白"""
        return self.prompts.get("opening", "你好，面试开始。")

    def get_question_prefix(self) -> str:
        """获取提问前缀"""
        return self.prompts.get("question_prefix", "下一个问题：")

    def get_feedback(self, score: float) -> str:
        """
        根据分数获取反馈模板

        Args:
            score: 0-10分

        Returns:
            反馈文字
        """
        templates = self.prompts.get("feedback_templates", {})

        if score >= 8:
            return templates.get("high_score", "回答正确。")
        elif score >= 6:
            return templates.get("medium_score", "回答基本正确，但还可以更好。")
        else:
            return templates.get("low_score", "回答不够准确。")

    def get_closing(self) -> str:
        """获取结束语"""
        return self.prompts.get("closing", "面试结束，感谢你的参与。")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "traits": self.traits,
            "prompts": self.prompts,
            "evaluation_bias": self.evaluation_bias
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Personality":
        """从字典创建"""
        return cls(
            name=data["name"],
            description=data["description"],
            traits=data["traits"],
            prompts=data["prompts"],
            evaluation_bias=data.get("evaluation_bias", {})
        )
