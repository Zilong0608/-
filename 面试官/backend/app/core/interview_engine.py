# -*- coding: utf-8 -*-
"""
面试引擎 - 核心流程控制
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Tuple

from ..models import (
    InterviewSession, InterviewConfig, InterviewStatus,
    Question, AnswerRecord, EvaluationResult, InterviewReport,
    Personality, DifficultyLevel
)
from ..services.question_service import QuestionRepository
from ..services.data_service import DataService
from ..core.personality_manager import PersonalityManager
from ..core.evaluation_engine import EvaluationEngine
from ..services.ai_service import AIService
from ..utils.prompts import build_final_report_prompt
from ..utils.logger import get_logger
from ..utils.exceptions import (
    SessionNotFoundException,
    QuestionPoolEmptyException,
    InvalidParameterException
)

logger = get_logger("interview_engine")


class InterviewEngine:
    """
    面试引擎 - 协调所有组件，控制面试流程
    """

    def __init__(
        self,
        question_repo: QuestionRepository,
        data_service: DataService,
        personality_manager: PersonalityManager,
        evaluation_engine: EvaluationEngine,
        ai_service: AIService
    ):
        """
        初始化

        Args:
            question_repo: 问题仓库
            data_service: 数据服务
            personality_manager: 人格管理器
            evaluation_engine: 评估引擎
            ai_service: AI服务
        """
        self.question_repo = question_repo
        self.data_service = data_service
        self.personality_manager = personality_manager
        self.evaluation_engine = evaluation_engine
        self.ai_service = ai_service

        # 运行时会话缓存
        self.active_sessions: Dict[str, InterviewSession] = {}

        logger.info("InterviewEngine initialized")

    def create_session(
        self,
        job_type: str,
        difficulty: DifficultyLevel,
        max_questions: int = 20,
        personality_name: Optional[str] = None,
        duration_minutes: int = 30
    ) -> InterviewSession:
        """
        创建面试会话

        Args:
            job_type: 岗位类型
            difficulty: 难度级别
            max_questions: 最大题目数
            personality_name: 指定人格名称，None则随机选择
            duration_minutes: 面试时长（分钟）

        Returns:
            面试会话对象

        Raises:
            InvalidParameterException: 参数无效
        """
        logger.info(
            f"Creating interview session: job={job_type}, "
            f"difficulty={difficulty.value}, max_questions={max_questions}"
        )

        # 验证参数
        if max_questions <= 0:
            raise InvalidParameterException(
                "max_questions",
                "must be greater than 0"
            )

        # 选择人格
        if personality_name:
            personality = self.personality_manager.get_personality_by_name(personality_name)
            if not personality:
                raise InvalidParameterException(
                    "personality_name",
                    f"personality '{personality_name}' not found"
                )
        else:
            personality = self.personality_manager.get_random_personality()

        # 创建配置
        config = InterviewConfig(
            job_type=job_type,
            difficulty=difficulty,
            duration_minutes=duration_minutes,
            max_questions=max_questions
        )

        # 创建会话
        session = InterviewSession(
            session_id=str(uuid.uuid4()),
            config=config,
            personality=personality,
            status=InterviewStatus.IDLE,
            preloaded_questions=[],
            answer_records=[],
            # 占位时间，数据库 start_time 不允许为空；正式开始会在 start_interview 覆盖
            start_time=datetime.now(),
            end_time=None
        )

        # 保存到缓存
        self.active_sessions[session.session_id] = session

        # 保存到数据库
        self.data_service.save_session(session)

        logger.info(
            f"Session created: {session.session_id} "
            f"with personality '{personality.name}'"
        )

        return session

    def start_interview(self, session_id: str) -> Tuple[str, str]:
        """
        启动面试

        Args:
            session_id: 会话ID

        Returns:
            (开场白, 第一个问题)

        Raises:
            SessionNotFoundException: 会话不存在
            QuestionPoolEmptyException: 问题池为空
        """
        logger.info(f"Starting interview: {session_id}")

        session = self._get_session(session_id)

        if session.status != InterviewStatus.IDLE:
            logger.warning(f"Session {session_id} already started")
            raise InvalidParameterException(
                "session_id",
                f"session is not in IDLE state (current: {session.status.value})"
            )

        # 更新状态
        session.status = InterviewStatus.PREPARING
        self.data_service.save_session(session)

        # 预加载问题
        try:
            session.preloaded_questions = self.question_repo.preload_questions(
                job_type=session.config.job_type,
                difficulty=session.config.difficulty
            )
        except QuestionPoolEmptyException as e:
            session.status = InterviewStatus.IDLE
            self.data_service.save_session(session)
            raise e

        # 更新状态为进行中
        session.status = InterviewStatus.IN_PROGRESS
        session.start_time = datetime.now()
        self.data_service.save_session(session)

        # 生成开场白
        opening = self.personality_manager.generate_opening(
            session.personality,
            session.config.job_type
        )

        # 获取第一个问题
        first_question = self._get_next_question_internal(session)
        if not first_question:
            raise QuestionPoolEmptyException("Failed to get first question")

        session.current_question = first_question
        if first_question.question_id not in session.asked_question_ids:
            session.asked_question_ids.append(first_question.question_id)

        logger.info(f"Interview started: {session_id}")

        return opening, first_question.content

    def submit_answer(
        self,
        session_id: str,
        answer: str
    ) -> Dict:
        """
        提交答案

        Args:
            session_id: 会话ID
            answer: 用户答案

        Returns:
            结果字典，包含评估结果和可能的追问

        Raises:
            SessionNotFoundException: 会话不存在
        """
        logger.info(f"Submitting answer for session: {session_id}")

        session = self._get_session(session_id)

        if session.status != InterviewStatus.IN_PROGRESS:
            raise InvalidParameterException(
                "session_id",
                f"session is not in progress (current: {session.status.value})"
            )

        if not session.current_question:
            raise InvalidParameterException(
                "session_id",
                "no current question to answer"
            )

        current_question = session.current_question

        # 1. 保存答题记录
        answer_record = AnswerRecord(
            question=current_question,
            user_answer=answer,
            is_followup=False,
            parent_question_id=None,
            answer_time=datetime.now()
        )
        session.answer_records.append(answer_record)
        self.data_service.save_answer_record(session_id, answer_record)

        # 2. 评估答案
        evaluation = self.evaluation_engine.evaluate_answer(
            question=current_question,
            user_answer=answer,
            personality=session.personality,
            job_type=session.config.job_type
        )

        # 保存评估结果
        self.data_service.save_evaluation(
            session_id,
            current_question.question_id,
            evaluation
        )

        # 3. 生成人格化反馈
        feedback = self.personality_manager.generate_feedback(
            session.personality,
            evaluation.total_score
        )

        # 4. 检查是否需要追问
        followup_question = None
        if evaluation.needs_followup:
            followup_question = self.evaluation_engine.generate_followup(
                question=current_question,
                user_answer=answer,
                evaluation=evaluation,
                personality=session.personality
            )

            if followup_question:
                # 创建追问的 Question 对象
                followup_q = Question(
                    question_id=f"{current_question.question_id}_followup",
                    content=followup_question,
                    reference_answer="",  # 追问没有标准答案
                    question_type=current_question.question_type,
                    difficulty=current_question.difficulty,
                    keywords=[],
                    job_category=current_question.job_category
                )
                session.current_question = followup_q
                session.is_answering_followup = True

        # 5. 如果没有追问，准备下一题
        if not followup_question:
            session.is_answering_followup = False

        return {
            "evaluation": {
                "total_score": evaluation.total_score,
                "technical_accuracy": evaluation.technical_accuracy,
                "clarity": evaluation.clarity,
                "depth_breadth": evaluation.depth_breadth,
                "keyword_coverage": evaluation.keyword_coverage,
                "weaknesses": evaluation.weaknesses,
                "suggestions": evaluation.suggestions
            },
            "feedback": feedback,
            "followup_question": followup_question,
            "has_followup": followup_question is not None
        }

    def submit_answer_async(
        self,
        session_id: str,
        answer: str
    ) -> Dict:
        """
        å¼‚æ­¥æäº¤ç­”æ¡ˆï¼ˆä¸åŒæ­¥è¯„ä¼°ï¼‰
        """
        logger.info(f"Submitting answer async for session: {session_id}")

        session = self._get_session(session_id)

        if session.status != InterviewStatus.IN_PROGRESS:
            raise InvalidParameterException(
                "session_id",
                f"session is not in progress (current: {session.status.value})"
            )

        if not session.current_question:
            raise InvalidParameterException(
                "session_id",
                "no current question to answer"
            )

        current_question = session.current_question
        is_followup = session.is_answering_followup
        parent_question_id = None
        if is_followup:
            parent_question_id = current_question.question_id.replace("_followup", "")

        answer_record = AnswerRecord(
            question=current_question,
            user_answer=answer,
            is_followup=is_followup,
            parent_question_id=parent_question_id,
            answer_time=datetime.now()
        )
        session.answer_records.append(answer_record)
        self.data_service.save_answer_record(session_id, answer_record)

        session.is_answering_followup = False

        return {
            "question": current_question,
            "personality": session.personality,
            "job_type": session.config.job_type,
            "should_evaluate": not is_followup
        }

    def evaluate_answer_async(
        self,
        session_id: str,
        question: Question,
        user_answer: str,
        personality: Personality,
        job_type: str
    ) -> None:
        """
        åŽå°è¯„ä¼°å¹¶ä¿å­˜ç»“æž?
        """
        try:
            evaluation = self.evaluation_engine.evaluate_answer(
                question=question,
                user_answer=user_answer,
                personality=personality,
                job_type=job_type
            )
            self.data_service.save_evaluation(
                session_id,
                question.question_id,
                evaluation
            )
        except Exception as e:
            logger.error(f"Async evaluation failed: {e}")

    def submit_followup_answer(
        self,
        session_id: str,
        answer: str
    ) -> Dict:
        """
        提交追问的答案

        Args:
            session_id: 会话ID
            answer: 用户答案

        Returns:
            结果字典

        Raises:
            SessionNotFoundException: 会话不存在
        """
        logger.info(f"Submitting followup answer for session: {session_id}")

        session = self._get_session(session_id)

        if not session.is_answering_followup:
            raise InvalidParameterException(
                "session_id",
                "not in followup mode"
            )

        # 保存追问答题记录
        answer_record = AnswerRecord(
            question=session.current_question,
            user_answer=answer,
            is_followup=True,
            parent_question_id=session.current_question.question_id.replace("_followup", ""),
            answer_time=datetime.now()
        )
        session.answer_records.append(answer_record)
        self.data_service.save_answer_record(session_id, answer_record)

        # 追问不进行详细评估，简单反馈即可
        session.is_answering_followup = False

        return {
            "message": "追问答案已记录",
            "feedback": "好的，我们继续下一题。"
        }

    def get_next_question(self, session_id: str) -> Optional[str]:
        """
        获取下一个问题

        Args:
            session_id: 会话ID

        Returns:
            下一个问题内容，如果没有更多问题返回None

        Raises:
            SessionNotFoundException: 会话不存在
        """
        logger.info(f"Getting next question for session: {session_id}")

        session = self._get_session(session_id)

        if session.status != InterviewStatus.IN_PROGRESS:
            raise InvalidParameterException(
                "session_id",
                "session is not in progress"
            )

        # 检查是否达到最大题数（跳过也算已问）
        if not session.asked_question_ids and session.answer_records:
            session.asked_question_ids = [
                record.question.question_id
                for record in session.answer_records
                if not record.is_followup
            ]
        main_questions_count = len(session.asked_question_ids)

        if main_questions_count >= session.config.max_questions:
            logger.info(f"Reached max questions ({session.config.max_questions})")
            return None

        # 获取下一题
        next_question = self._get_next_question_internal(session)
        if not next_question:
            logger.warning("No more questions available")
            return None

        session.current_question = next_question
        if next_question.question_id not in session.asked_question_ids:
            session.asked_question_ids.append(next_question.question_id)
        return next_question.content

    def end_interview(self, session_id: str) -> InterviewReport:
        """
        结束面试，生成报告

        Args:
            session_id: 会话ID

        Returns:
            面试报告

        Raises:
            SessionNotFoundException: 会话不存在
        """
        logger.info(f"Ending interview: {session_id}")

        session = self._get_session(session_id)

        if session.status == InterviewStatus.COMPLETED:
            logger.warning(f"Session {session_id} already completed")
            # 返回已有报告
            report_data = self.data_service.get_report(session_id)
            if report_data:
                return self._dict_to_report(report_data)

        # 更新状态
        session.status = InterviewStatus.COMPLETED
        session.end_time = datetime.now()
        self.data_service.save_session(session)

        # 获取所有评估结果
        evaluations_data = self.data_service.get_evaluations(session_id)
        evaluations = [self._dict_to_evaluation(e) for e in evaluations_data]

        if not evaluations:
            logger.warning(f"No evaluations found for session {session_id}")
            total_time_minutes = session.get_elapsed_minutes()
            empty_report = InterviewReport(
                session_id=session.session_id,
                job_type=session.config.job_type,
                personality_name=session.personality.name,
                overall_score=0.0,
                avg_technical_accuracy=0.0,
                avg_clarity=0.0,
                avg_depth_breadth=0.0,
                avg_keyword_coverage=0.0,
                total_questions=0,
                correct_count=0,
                partial_correct_count=0,
                incorrect_count=0,
                correct_rate=0.0,
                total_time_minutes=total_time_minutes,
                avg_time_per_question=0.0,
                weak_areas=["未完成任何题目"],
                strong_areas=[],
                suggestions=["建议重新开始面试"],
                answer_records=[]
            )
            self.data_service.save_report(session_id, empty_report)
            return empty_report

        # 计算统计数据
        stats = self.evaluation_engine.calculate_statistics(evaluations)

        # 构建答题详情文本
        answer_details = self._build_answer_details(session.answer_records, evaluations)

        # 构建报告生成 prompt
        prompt = build_final_report_prompt(
            job_type=session.config.job_type,
            difficulty=session.config.difficulty.value,
            total_questions=len(evaluations),
            correct_rate=stats['pass_rate'],
            avg_technical=stats['avg_technical_accuracy'],
            avg_clarity=stats['avg_clarity'],
            avg_depth=stats['avg_depth_breadth'],
            answer_details=answer_details
        )

        # 调用 AI 生成报告内容
        try:
            ai_report = self.ai_service.generate_report(prompt)
        except Exception as e:
            logger.error(f"Failed to generate AI report: {e}")
            # 使用默认报告
            ai_report = {
                "weak_areas": ["报告生成失败"],
                "strong_areas": [],
                "suggestions": ["请重试"]
            }

        total_questions = len(evaluations)
        correct_count = sum(1 for e in evaluations if e.total_score >= 8.0)
        partial_correct_count = sum(1 for e in evaluations if 6.0 <= e.total_score < 8.0)
        incorrect_count = sum(1 for e in evaluations if e.total_score < 6.0)
        avg_keyword_coverage = (
            sum(e.keyword_coverage for e in evaluations) / total_questions
            if total_questions else 0.0
        )
        total_time_minutes = session.get_elapsed_minutes()
        avg_time_per_question = (
            round(total_time_minutes / total_questions, 2)
            if total_questions else 0.0
        )

        report = InterviewReport(
            session_id=session.session_id,
            job_type=session.config.job_type,
            personality_name=session.personality.name,
            overall_score=stats['avg_total_score'],
            avg_technical_accuracy=stats['avg_technical_accuracy'],
            avg_clarity=stats['avg_clarity'],
            avg_depth_breadth=stats['avg_depth_breadth'],
            avg_keyword_coverage=round(avg_keyword_coverage, 2),
            total_questions=total_questions,
            correct_count=correct_count,
            partial_correct_count=partial_correct_count,
            incorrect_count=incorrect_count,
            correct_rate=stats['pass_rate'],
            total_time_minutes=total_time_minutes,
            avg_time_per_question=avg_time_per_question,
            weak_areas=ai_report.get('weak_areas', []),
            strong_areas=ai_report.get('strong_areas', []),
            suggestions=ai_report.get('suggestions', []),
            answer_records=session.answer_records
        )

        # 保存报告
        self.data_service.save_report(session_id, report)

        logger.info(f"Interview completed: {session_id}")

        # 从活跃会话中移除
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]

        return report

    def get_session_status(self, session_id: str) -> Dict:
        """
        获取会话状态

        Args:
            session_id: 会话ID

        Returns:
            状态信息字典
        """
        session = self._get_session(session_id)

        main_questions_answered = sum(
            1 for record in session.answer_records
            if not record.is_followup
        )

        return {
            "session_id": session.session_id,
            "status": session.status.value,
            "personality": session.personality.name,
            "job_type": session.config.job_type,
            "difficulty": session.config.difficulty.value,
            "questions_answered": main_questions_answered,
            "max_questions": session.config.max_questions,
            "is_answering_followup": session.is_answering_followup,
            "start_time": session.start_time.isoformat() if session.start_time else None,
            "end_time": session.end_time.isoformat() if session.end_time else None
        }

    def _get_session(self, session_id: str) -> InterviewSession:
        """
        获取会话（优先从缓存，否则从数据库）

        Args:
            session_id: 会话ID

        Returns:
            会话对象

        Raises:
            SessionNotFoundException: 会话不存在
        """
        # 先查缓存
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]

        # 从数据库加载
        session_data = self.data_service.get_session(session_id)
        if not session_data:
            raise SessionNotFoundException(session_id)

        # 重建会话对象（简化版，只包含必要信息）
        # 注意：实际使用中可能需要更完整的重建逻辑
        logger.warning(
            f"Session {session_id} loaded from database, "
            "some in-memory state may be lost"
        )
        raise SessionNotFoundException(session_id)  # 暂时不支持从数据库恢复

    def _get_next_question_internal(self, session: InterviewSession) -> Optional[Question]:
        """
        内部方法：获取下一个问题

        Args:
            session: 会话对象

        Returns:
            问题对象
        """
        # 收集已问过的问题ID
        asked_ids = session.asked_question_ids
        if not asked_ids:
            asked_ids = [
                record.question.question_id
                for record in session.answer_records
                if not record.is_followup
            ]

        # 从问题池获取
        return self.question_repo.get_next_question(
            exclude_ids=asked_ids,
            job_type=session.config.job_type,
            difficulty=session.config.difficulty
        )

    def _build_answer_details(
        self,
        answer_records: list,
        evaluations: list
    ) -> str:
        """
        构建答题详情文本

        Args:
            answer_records: 答题记录列表
            evaluations: 评估结果列表

        Returns:
            详情文本
        """
        details = []

        # 只统计非追问题目
        main_records = [r for r in answer_records if not r.is_followup]

        for i, record in enumerate(main_records, 1):
            # 找到对应的评估结果
            eval_result = next(
                (e for e in evaluations if e.technical_accuracy >= 0),  # 简化匹配
                None
            )

            if eval_result:
                details.append(
                    f"题目{i}：{record.question.content[:50]}...\n"
                    f"  得分：{eval_result.total_score:.1f}/10\n"
                    f"  主要不足：{', '.join(eval_result.weaknesses[:2])}\n"
                )

        return "\n".join(details) if details else "无答题记录"

    def _dict_to_evaluation(self, data: Dict) -> EvaluationResult:
        """将字典转换为 EvaluationResult 对象"""
        return EvaluationResult(
            question_id=data.get('question_id', ''),
            user_answer=data.get('user_answer', ''),
            technical_accuracy=data['technical_accuracy'],
            clarity=data['clarity'],
            depth_breadth=data['depth_breadth'],
            keywords_hit=data['keywords_hit'],
            keywords_missed=data['keywords_missed'],
            keyword_coverage=data['keyword_coverage'],
            weaknesses=data['weaknesses'],
            suggestions=data['suggestions'],
            total_score=data['total_score'],
            needs_followup=data['needs_followup']
        )

    def _dict_to_report(self, data: Dict) -> InterviewReport:
        """将字典转换为 InterviewReport 对象"""
        return InterviewReport(
            session_id=data.get('session_id', ''),
            job_type=data.get('job_type', ''),
            personality_name=data.get('personality_name', ''),
            overall_score=data.get('overall_score', 0.0),
            avg_technical_accuracy=data.get('avg_technical_accuracy', 0.0),
            avg_clarity=data.get('avg_clarity', 0.0),
            avg_depth_breadth=data.get('avg_depth_breadth', 0.0),
            avg_keyword_coverage=data.get('avg_keyword_coverage', 0.0),
            total_questions=data.get('total_questions', 0),
            correct_count=data.get('correct_count', 0),
            partial_correct_count=data.get('partial_correct_count', 0),
            incorrect_count=data.get('incorrect_count', 0),
            correct_rate=data.get('correct_rate', 0.0),
            total_time_minutes=data.get('total_time_minutes', 0.0),
            avg_time_per_question=data.get('avg_time_per_question', 0.0),
            weak_areas=data.get('weak_areas', []),
            strong_areas=data.get('strong_areas', []),
            suggestions=data.get('suggestions', []),
            answer_records=data.get('answer_records', [])
        )
