# -*- coding: utf-8 -*-
"""
数据持久化服务 - SQLite 存储
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict

from ..models import (
    InterviewSession, InterviewConfig, InterviewStatus,
    AnswerRecord, EvaluationResult, InterviewReport,
    Question, Personality
)
from ..utils.logger import get_logger
from ..utils.exceptions import InterviewException

logger = get_logger("data_service")


class DataService:
    """
    数据服务 - 负责所有数据持久化操作
    """

    def __init__(self, db_path: str):
        """
        初始化

        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()
        logger.info(f"DataService initialized with database: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """初始化数据库表结构"""
        logger.info("Initializing database schema...")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 面试会话表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interview_sessions (
                    session_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    max_questions INTEGER NOT NULL,
                    personality_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            # 答题记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS answer_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    question_content TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    reference_answer TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    is_followup BOOLEAN NOT NULL,
                    parent_question_id TEXT,
                    answer_time TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES interview_sessions(session_id)
                )
            """)

            # 评估结果表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    technical_accuracy REAL NOT NULL,
                    clarity REAL NOT NULL,
                    depth_breadth REAL NOT NULL,
                    keyword_coverage REAL NOT NULL,
                    keywords_hit TEXT,
                    keywords_missed TEXT,
                    weaknesses TEXT,
                    suggestions TEXT,
                    total_score REAL NOT NULL,
                    needs_followup BOOLEAN NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES interview_sessions(session_id)
                )
            """)

            # 面试报告表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interview_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    overall_score REAL NOT NULL,
                    avg_technical_accuracy REAL NOT NULL,
                    avg_clarity REAL NOT NULL,
                    avg_depth_breadth REAL NOT NULL,
                    correct_rate REAL NOT NULL,
                    weak_areas TEXT,
                    strong_areas TEXT,
                    suggestions TEXT,
                    generated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES interview_sessions(session_id)
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_status
                ON interview_sessions(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_answers_session
                ON answer_records(session_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_evaluations_session
                ON evaluation_results(session_id)
            """)

            conn.commit()
            logger.info("Database schema initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            conn.rollback()
            raise InterviewException(f"Database initialization failed: {e}")
        finally:
            conn.close()

    def save_session(self, session: InterviewSession):
        """
        保存面试会话

        Args:
            session: 面试会话对象
        """
        logger.debug(f"Saving session: {session.session_id}")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO interview_sessions
                (session_id, job_type, difficulty, max_questions, personality_name,
                 status, start_time, end_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                session.config.job_type,
                session.config.difficulty.value,
                session.config.max_questions,
                session.personality.name,
                session.status.value,
                session.start_time.isoformat() if session.start_time else None,
                session.end_time.isoformat() if session.end_time else None,
                datetime.now().isoformat()
            ))

            conn.commit()
            logger.debug(f"Session saved: {session.session_id}")

        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            conn.rollback()
            raise InterviewException(f"Failed to save session: {e}")
        finally:
            conn.close()

    def save_answer_record(self, session_id: str, record: AnswerRecord):
        """
        保存答题记录

        Args:
            session_id: 会话ID
            record: 答题记录
        """
        logger.debug(f"Saving answer record for question: {record.question.question_id}")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO answer_records
                (session_id, question_id, question_content, question_type, difficulty,
                 reference_answer, user_answer, is_followup, parent_question_id, answer_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                record.question.question_id,
                record.question.content,
                record.question.question_type.value,
                record.question.difficulty.value,
                record.question.reference_answer,
                record.user_answer,
                record.is_followup,
                record.parent_question_id,
                record.answer_time.isoformat()
            ))

            conn.commit()
            logger.debug(f"Answer record saved for question: {record.question.question_id}")

        except Exception as e:
            logger.error(f"Failed to save answer record: {e}")
            conn.rollback()
            raise InterviewException(f"Failed to save answer record: {e}")
        finally:
            conn.close()

    def save_evaluation(self, session_id: str, question_id: str, evaluation: EvaluationResult):
        """
        保存评估结果

        Args:
            session_id: 会话ID
            question_id: 问题ID
            evaluation: 评估结果
        """
        logger.debug(f"Saving evaluation for question: {question_id}")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO evaluation_results
                (session_id, question_id, technical_accuracy, clarity, depth_breadth,
                 keyword_coverage, keywords_hit, keywords_missed, weaknesses, suggestions,
                 total_score, needs_followup, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                question_id,
                evaluation.technical_accuracy,
                evaluation.clarity,
                evaluation.depth_breadth,
                evaluation.keyword_coverage,
                json.dumps(evaluation.keywords_hit, ensure_ascii=False),
                json.dumps(evaluation.keywords_missed, ensure_ascii=False),
                json.dumps(evaluation.weaknesses, ensure_ascii=False),
                json.dumps(evaluation.suggestions, ensure_ascii=False),
                evaluation.total_score,
                evaluation.needs_followup,
                datetime.now().isoformat()
            ))

            conn.commit()
            logger.debug(f"Evaluation saved for question: {question_id}")

        except Exception as e:
            logger.error(f"Failed to save evaluation: {e}")
            conn.rollback()
            raise InterviewException(f"Failed to save evaluation: {e}")
        finally:
            conn.close()

    def save_report(self, session_id: str, report: InterviewReport):
        """
        保存面试报告

        Args:
            session_id: 会话ID
            report: 面试报告
        """
        logger.debug(f"Saving report for session: {session_id}")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO interview_reports
                (session_id, overall_score, avg_technical_accuracy, avg_clarity,
                 avg_depth_breadth, correct_rate, weak_areas, strong_areas,
                 suggestions, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                report.overall_score,
                report.avg_technical_accuracy,
                report.avg_clarity,
                report.avg_depth_breadth,
                report.correct_rate,
                json.dumps(report.weak_areas, ensure_ascii=False),
                json.dumps(report.strong_areas, ensure_ascii=False),
                json.dumps(report.suggestions, ensure_ascii=False),
                datetime.now().isoformat()
            ))

            conn.commit()
            logger.debug(f"Report saved for session: {session_id}")

        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            conn.rollback()
            raise InterviewException(f"Failed to save report: {e}")
        finally:
            conn.close()

    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        获取面试会话

        Args:
            session_id: 会话ID

        Returns:
            会话数据字典，如果不存在返回None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM interview_sessions WHERE session_id = ?
            """, (session_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

        finally:
            conn.close()

    def get_answer_records(self, session_id: str) -> List[Dict]:
        """
        获取会话的所有答题记录

        Args:
            session_id: 会话ID

        Returns:
            答题记录列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM answer_records
                WHERE session_id = ?
                ORDER BY answer_time ASC
            """, (session_id,))

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_evaluations(self, session_id: str) -> List[Dict]:
        """
        获取会话的所有评估结果

        Args:
            session_id: 会话ID

        Returns:
            评估结果列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM evaluation_results
                WHERE session_id = ?
                ORDER BY created_at ASC
            """, (session_id,))

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # 解析 JSON 字段
                result['keywords_hit'] = json.loads(result['keywords_hit'])
                result['keywords_missed'] = json.loads(result['keywords_missed'])
                result['weaknesses'] = json.loads(result['weaknesses'])
                result['suggestions'] = json.loads(result['suggestions'])
                results.append(result)

            return results

        finally:
            conn.close()

    def get_evaluation(self, session_id: str, question_id: str) -> Optional[Dict]:
        """
        èŽ·å–æŒ‡å®šé¢˜ç›®çš„è¯„ä¼°ç»“æž?
        Args:
            session_id: ä¼šè¯ID
            question_id: é—®é¢˜ID

        Returns:
            è¯„ä¼°ç»“æžœå­—å…¸ï¼Œå¦‚æžœä¸å­˜åœ¨è¿”å›žNone
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM evaluation_results
                WHERE session_id = ? AND question_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id, question_id))

            row = cursor.fetchone()
            if not row:
                return None

            result = dict(row)
            result['keywords_hit'] = json.loads(result['keywords_hit'])
            result['keywords_missed'] = json.loads(result['keywords_missed'])
            result['weaknesses'] = json.loads(result['weaknesses'])
            result['suggestions'] = json.loads(result['suggestions'])
            return result

        finally:
            conn.close()

    def get_report(self, session_id: str) -> Optional[Dict]:
        """
        获取面试报告

        Args:
            session_id: 会话ID

        Returns:
            报告数据字典，如果不存在返回None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM interview_reports WHERE session_id = ?
            """, (session_id,))

            row = cursor.fetchone()
            if row:
                report = dict(row)
                # 解析 JSON 字段
                report['weak_areas'] = json.loads(report['weak_areas'])
                report['strong_areas'] = json.loads(report['strong_areas'])
                report['suggestions'] = json.loads(report['suggestions'])
                return report
            return None

        finally:
            conn.close()

    def list_sessions(
        self,
        status: Optional[InterviewStatus] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        列出面试会话

        Args:
            status: 状态过滤
            limit: 返回数量限制

        Returns:
            会话列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if status:
                cursor.execute("""
                    SELECT * FROM interview_sessions
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (status.value, limit))
            else:
                cursor.execute("""
                    SELECT * FROM interview_sessions
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_statistics(self) -> Dict:
        """
        获取统计数据

        Returns:
            统计数据字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 总面试次数
            cursor.execute("SELECT COUNT(*) FROM interview_sessions")
            total_sessions = cursor.fetchone()[0]

            # 已完成面试次数
            cursor.execute("""
                SELECT COUNT(*) FROM interview_sessions
                WHERE status = 'completed'
            """)
            completed_sessions = cursor.fetchone()[0]

            # 总答题数
            cursor.execute("SELECT COUNT(*) FROM answer_records")
            total_answers = cursor.fetchone()[0]

            # 平均分
            cursor.execute("SELECT AVG(total_score) FROM evaluation_results")
            avg_score = cursor.fetchone()[0] or 0.0

            # 通过率
            cursor.execute("""
                SELECT
                    COUNT(CASE WHEN total_score >= 6.0 THEN 1 END) * 1.0 / COUNT(*)
                FROM evaluation_results
            """)
            pass_rate = cursor.fetchone()[0] or 0.0

            return {
                "total_sessions": total_sessions,
                "completed_sessions": completed_sessions,
                "total_answers": total_answers,
                "avg_score": round(avg_score, 2),
                "pass_rate": round(pass_rate, 2)
            }

        finally:
            conn.close()

    def delete_session(self, session_id: str):
        """
        删除面试会话及相关数据

        Args:
            session_id: 会话ID
        """
        logger.info(f"Deleting session: {session_id}")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM interview_reports WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM evaluation_results WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM answer_records WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM interview_sessions WHERE session_id = ?", (session_id,))

            conn.commit()
            logger.info(f"Session deleted: {session_id}")

        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            conn.rollback()
            raise InterviewException(f"Failed to delete session: {e}")
        finally:
            conn.close()
