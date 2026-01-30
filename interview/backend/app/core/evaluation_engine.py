# -*- coding: utf-8 -*-
"""
评估引擎 - 答案评估和追问生成
"""

from typing import Dict, Tuple, Optional

from ..models import Question, Personality, EvaluationResult
from ..services.ai_service import AIService
from ..core.personality_manager import PersonalityManager
from ..utils.prompts import build_evaluation_prompt, build_followup_prompt
from ..utils.logger import get_logger
from ..utils.exceptions import AIServiceException

logger = get_logger("evaluation_engine")


class EvaluationEngine:
    """
    评估引擎 - 负责答案评估和追问生成
    """

    def __init__(
        self,
        ai_service: AIService,
        personality_manager: PersonalityManager,
        followup_score_threshold: Tuple[float, float] = (6.0, 8.0)
    ):
        """
        初始化

        Args:
            ai_service: AI服务实例
            personality_manager: 人格管理器实例
            followup_score_threshold: 追问得分阈值 (min, max)，得分在此区间内时生成追问
        """
        self.ai_service = ai_service
        self.personality_manager = personality_manager
        self.followup_score_min = followup_score_threshold[0]
        self.followup_score_max = followup_score_threshold[1]

        logger.info(
            f"EvaluationEngine initialized with followup threshold: "
            f"[{self.followup_score_min}, {self.followup_score_max}]"
        )

    def evaluate_answer(
        self,
        question: Question,
        user_answer: str,
        personality: Personality,
        job_type: str
    ) -> EvaluationResult:
        """
        评估候选人答案

        Args:
            question: 问题对象
            user_answer: 用户答案
            personality: 面试官人格
            job_type: 岗位类型

        Returns:
            评估结果

        Raises:
            AIServiceException: AI评估失败
        """
        logger.info(f"Evaluating answer for question: {question.question_id}")

        try:
            # 1. 构建评估 prompt
            prompt = build_evaluation_prompt(
                job_type=job_type,
                question_type=question.question_type.value,
                difficulty=question.difficulty.value,
                question=question.content,
                reference_answer=question.reference_answer,
                user_answer=user_answer
            )

            # 2. 调用 AI 评估
            ai_result = self.ai_service.evaluate_answer(prompt)

            # 3. 提取评分
            scores = {
                "technical_accuracy": float(ai_result.get("technical_accuracy", 0)),
                "clarity": float(ai_result.get("clarity", 0)),
                "depth_breadth": float(ai_result.get("depth_breadth", 0))
            }

            # 4. 应用人格评分倾向
            adjusted_scores = self.personality_manager.apply_evaluation_bias(
                personality,
                scores
            )

            # 5. 计算关键词覆盖率
            keywords_hit = ai_result.get("keywords_hit", [])
            keywords_missed = ai_result.get("keywords_missed", [])
            keyword_coverage = self._calculate_keyword_coverage(
                keywords_hit,
                keywords_missed
            )

            # 6. 计算总分（加权平均）
            total_score = self._calculate_total_score(adjusted_scores)

            # 7. 判断是否需要追问
            needs_followup = self._should_generate_followup(total_score)

            # 8. 构建评估结果
            result = EvaluationResult(
                question_id=question.question_id,
                user_answer=user_answer,
                technical_accuracy=adjusted_scores["technical_accuracy"],
                clarity=adjusted_scores["clarity"],
                depth_breadth=adjusted_scores["depth_breadth"],
                keywords_hit=keywords_hit,
                keywords_missed=keywords_missed,
                keyword_coverage=keyword_coverage,
                weaknesses=ai_result.get("weaknesses", []),
                suggestions=ai_result.get("suggestions", []),
                total_score=total_score,
                needs_followup=needs_followup
            )

            logger.info(
                f"Evaluation completed: total_score={total_score:.2f}, "
                f"needs_followup={needs_followup}"
            )

            return result

        except AIServiceException as e:
            logger.error(f"AI evaluation failed: {e}")
            return self._fallback_evaluation(
                question=question,
                user_answer=user_answer,
                reason=str(e)
            )
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            return self._fallback_evaluation(
                question=question,
                user_answer=user_answer,
                reason=str(e)
            )

    def _fallback_evaluation(
        self,
        question: Question,
        user_answer: str,
        reason: str
    ) -> EvaluationResult:
        logger.warning(f"Using fallback evaluation due to error: {reason}")
        return EvaluationResult(
            question_id=question.question_id,
            user_answer=user_answer,
            technical_accuracy=0.0,
            clarity=0.0,
            depth_breadth=0.0,
            keywords_hit=[],
            keywords_missed=[],
            keyword_coverage=0.0,
            weaknesses=["AI evaluation unavailable"],
            suggestions=["Please try again when the AI service is available."],
            total_score=0.0,
            needs_followup=False
        )

    def generate_followup(
        self,
        question: Question,
        user_answer: str,
        evaluation: EvaluationResult,
        personality: Personality
    ) -> Optional[str]:
        """
        生成追问

        Args:
            question: 原始问题
            user_answer: 用户答案
            evaluation: 评估结果
            personality: 面试官人格

        Returns:
            追问内容，如果不需要追问则返回None

        Raises:
            AIServiceException: AI生成失败
        """
        if not evaluation.needs_followup:
            logger.debug("No followup needed based on evaluation")
            return None

        logger.info(f"Generating followup for question: {question.question_id}")

        try:
            # 获取追问风格
            followup_style = self.personality_manager.get_followup_style(personality)

            # 构建追问 prompt
            prompt = build_followup_prompt(
                personality_name=personality.name,
                question=question.content,
                user_answer=user_answer,
                total_score=evaluation.total_score,
                weaknesses=evaluation.weaknesses,
                followup_style=followup_style
            )

            # 调用 AI 生成追问
            followup = self.ai_service.generate_followup(prompt)

            logger.info(f"Followup generated: {followup[:50]}...")
            return followup

        except AIServiceException as e:
            logger.error(f"Failed to generate followup: {e}")
            # 追问生成失败不应阻断面试流程，返回 None
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating followup: {e}")
            return None

    def _calculate_keyword_coverage(
        self,
        keywords_hit: list,
        keywords_missed: list
    ) -> float:
        """
        计算关键词覆盖率

        Args:
            keywords_hit: 命中的关键词
            keywords_missed: 遗漏的关键词

        Returns:
            覆盖率（0-1）
        """
        total = len(keywords_hit) + len(keywords_missed)
        if total == 0:
            return 1.0  # 没有关键词要求，视为全覆盖

        coverage = len(keywords_hit) / total
        return round(coverage, 2)

    def _calculate_total_score(self, scores: Dict[str, float]) -> float:
        """
        计算总分（加权平均）

        Args:
            scores: 各维度得分

        Returns:
            总分（0-10）
        """
        # 权重配置：技术准确性 > 深度广度 > 表达清晰度
        weights = {
            "technical_accuracy": 0.5,
            "clarity": 0.2,
            "depth_breadth": 0.3
        }

        total = sum(
            scores[key] * weight
            for key, weight in weights.items()
        )

        return round(total, 2)

    def _should_generate_followup(self, total_score: float) -> bool:
        """
        判断是否需要生成追问

        Args:
            total_score: 总分

        Returns:
            是否需要追问
        """
        # 得分在阈值区间内，说明回答"不够好但也不太差"，适合追问
        return self.followup_score_min <= total_score <= self.followup_score_max

    def calculate_statistics(
        self,
        evaluations: list[EvaluationResult]
    ) -> Dict:
        """
        计算统计数据

        Args:
            evaluations: 评估结果列表

        Returns:
            统计数据
        """
        if not evaluations:
            return {
                "avg_technical_accuracy": 0.0,
                "avg_clarity": 0.0,
                "avg_depth_breadth": 0.0,
                "avg_total_score": 0.0,
                "pass_rate": 0.0,
                "total_count": 0
            }

        total_count = len(evaluations)

        # 计算平均分
        avg_technical = sum(e.technical_accuracy for e in evaluations) / total_count
        avg_clarity = sum(e.clarity for e in evaluations) / total_count
        avg_depth = sum(e.depth_breadth for e in evaluations) / total_count
        avg_total = sum(e.total_score for e in evaluations) / total_count

        # 计算通过率（总分 >= 6.0 视为通过）
        pass_count = sum(1 for e in evaluations if e.total_score >= 6.0)
        pass_rate = pass_count / total_count

        return {
            "avg_technical_accuracy": round(avg_technical, 2),
            "avg_clarity": round(avg_clarity, 2),
            "avg_depth_breadth": round(avg_depth, 2),
            "avg_total_score": round(avg_total, 2),
            "pass_rate": round(pass_rate, 2),
            "total_count": total_count,
            "pass_count": pass_count
        }
