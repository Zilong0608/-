# -*- coding: utf-8 -*-
"""
人格管理器
"""

import random
import yaml
from pathlib import Path
from typing import Dict, Optional

from ..models import Personality
from ..utils.logger import get_logger
from ..utils.exceptions import ConfigurationException

logger = get_logger("personality_manager")


class PersonalityManager:
    """
    人格管理器 - 管理多种面试官人格
    """

    def __init__(self, personalities_dir: str):
        """
        初始化

        Args:
            personalities_dir: 人格配置文件目录
        """
        self.personalities_dir = Path(personalities_dir)
        self.personalities: Dict[str, Personality] = {}
        self._load_all_personalities()

    def _load_all_personalities(self):
        """加载所有人格配置文件"""
        if not self.personalities_dir.exists():
            raise ConfigurationException(
                f"Personalities directory not found: {self.personalities_dir}"
            )

        yaml_files = list(self.personalities_dir.glob("*.yaml"))
        if not yaml_files:
            raise ConfigurationException(
                f"No personality configuration files found in {self.personalities_dir}"
            )

        logger.info(f"Loading personalities from {self.personalities_dir}")

        for yaml_file in yaml_files:
            try:
                personality = self._load_personality_from_file(yaml_file)
                self.personalities[personality.name] = personality
                logger.info(f"Loaded personality: {personality.name}")
            except Exception as e:
                logger.error(f"Failed to load personality from {yaml_file}: {e}")

        if not self.personalities:
            raise ConfigurationException("No valid personalities loaded")

        logger.info(f"Total {len(self.personalities)} personalities loaded")

    def _load_personality_from_file(self, yaml_file: Path) -> Personality:
        """
        从YAML文件加载人格配置

        Args:
            yaml_file: YAML文件路径

        Returns:
            Personality对象
        """
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        return Personality(
            name=data["name"],
            description=data["description"],
            traits=data["traits"],
            prompts=data["prompts"],
            evaluation_bias=data.get("evaluation_bias", {})
        )

    def get_random_personality(self) -> Personality:
        """随机选择一个人格"""
        personality = random.choice(list(self.personalities.values()))
        logger.info(f"Randomly selected personality: {personality.name}")
        return personality

    def get_personality_by_name(self, name: str) -> Optional[Personality]:
        """
        通过名字获取人格

        Args:
            name: 人格名称

        Returns:
            Personality对象，如果不存在返回None
        """
        personality = self.personalities.get(name)
        if personality:
            logger.info(f"Selected personality: {name}")
        else:
            logger.warning(f"Personality not found: {name}")
        return personality

    def get_all_personality_names(self) -> list:
        """获取所有人格名称"""
        return list(self.personalities.keys())

    def generate_opening(self, personality: Personality, job_type: str) -> str:
        """
        生成开场白

        Args:
            personality: 人格对象
            job_type: 岗位类型

        Returns:
            开场白文字
        """
        opening = personality.get_opening()
        # 可以根据岗位类型做一些定制
        return opening

    def generate_question_prefix(self, personality: Personality) -> str:
        """
        生成提问前缀

        Args:
            personality: 人格对象

        Returns:
            提问前缀
        """
        return personality.get_question_prefix()

    def generate_feedback(
        self,
        personality: Personality,
        score: float
    ) -> str:
        """
        生成评价反馈

        Args:
            personality: 人格对象
            score: 得分（0-10）

        Returns:
            反馈文字
        """
        return personality.get_feedback(score)

    def get_followup_style(self, personality: Personality) -> str:
        """
        获取追问风格

        Args:
            personality: 人格对象

        Returns:
            追问风格描述
        """
        return personality.prompts.get(
            "followup_style",
            "针对性提问，深入考察候选人的理解"
        )

    def apply_evaluation_bias(
        self,
        personality: Personality,
        scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        应用人格评分倾向

        Args:
            personality: 人格对象
            scores: 原始评分 {"technical_accuracy": 8.0, ...}

        Returns:
            调整后的评分
        """
        bias = personality.evaluation_bias
        adjusted_scores = scores.copy()

        # 应用权重调整（-1到1之间）
        if "technical_weight" in bias:
            adjusted_scores["technical_accuracy"] = min(10, max(0,
                scores["technical_accuracy"] + bias["technical_weight"]
            ))

        if "clarity_weight" in bias:
            adjusted_scores["clarity"] = min(10, max(0,
                scores["clarity"] + bias["clarity_weight"]
            ))

        if "depth_weight" in bias:
            adjusted_scores["depth_breadth"] = min(10, max(0,
                scores["depth_breadth"] + bias["depth_weight"]
            ))

        return adjusted_scores
