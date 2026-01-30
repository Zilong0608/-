# -*- coding: utf-8 -*-
"""
API 请求/响应模型
"""

from typing import Optional, List
from pydantic import BaseModel, Field


# ============ 请求模型 ============

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    job_type: str = Field(..., description="岗位类型", example="后端开发")
    difficulty: str = Field(..., description="难度级别: 基础/进阶/高级 或 easy/medium/hard", example="进阶")
    max_questions: int = Field(10, ge=1, le=50, description="最大题目数")
    personality_name: Optional[str] = Field(None, description="指定人格名称，不指定则随机")
    question_category: Optional[str] = Field(None, description="????", example="LLM")


class SubmitAnswerRequest(BaseModel):
    """提交答案请求"""
    answer: str = Field(..., description="用户答案", min_length=1)


class TTSRequest(BaseModel):
    """TTS 请求"""
    text: str = Field(..., description="需要朗读的文本", min_length=1)
    model: Optional[str] = Field(None, description="TTS 模型，例如 gpt-4o-mini-tts")
    voice: Optional[str] = Field(None, description="声音，例如 alloy")
    format: Optional[str] = Field("mp3", description="音频格式：mp3/wav")
    speed: Optional[float] = Field(None, description="语速 0.5~2.0")


# ============ 响应模型 ============

class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    status: str
    personality: str
    job_type: str
    difficulty: str
    question_category: Optional[str]
    questions_answered: int
    max_questions: int
    start_time: Optional[str]
    end_time: Optional[str]


class StartInterviewResponse(BaseModel):
    """启动面试响应"""
    session_id: str
    opening: str
    first_question: str


class EvaluationResponse(BaseModel):
    """评估响应"""
    total_score: float
    technical_accuracy: float
    clarity: float
    depth_breadth: float
    keyword_coverage: float
    weaknesses: List[str]
    suggestions: List[str]


class SubmitAnswerResponse(BaseModel):
    """提交答案响应"""
    evaluation: EvaluationResponse
    feedback: str
    has_followup: bool
    followup_question: Optional[str]


class AsyncAnswerResponse(BaseModel):
    """异步提交响应"""
    queued: bool
    question_id: str


class EvaluationLookupResponse(BaseModel):
    """评估查询响应"""
    question_id: str
    has_evaluation: bool
    evaluation: Optional[EvaluationResponse]


class STTResponse(BaseModel):
    """语音转文字响应"""
    text: str


class NextQuestionResponse(BaseModel):
    """下一题响应"""
    has_next: bool
    question: Optional[str]
    questions_answered: int
    max_questions: int



class ReportDetailItem(BaseModel):
    """Report detail item"""
    question_id: Optional[str] = None
    question: str
    user_answer: str
    is_followup: Optional[bool] = False
    parent_question_id: Optional[str] = None
    total_score: float
    technical_accuracy: float
    clarity: float
    depth_breadth: float
    weaknesses: List[str]
    suggestions: List[str]
    llm_answer: str

class InterviewReportResponse(BaseModel):
    """面试报告响应"""
    session_id: str
    overall_score: float
    avg_technical_accuracy: float
    avg_clarity: float
    avg_depth_breadth: float
    correct_rate: float
    weak_areas: List[str]
    strong_areas: List[str]
    suggestions: List[str]
    details: Optional[List[ReportDetailItem]] = None


class PersonalityInfo(BaseModel):
    """人格信息"""
    name: str
    description: str


class StatisticsResponse(BaseModel):
    """统计数据响应"""
    total_sessions: int
    completed_sessions: int
    total_answers: int
    avg_score: float
    pass_rate: float


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    rag_connected: bool
    ai_connected: bool


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None

class QuestionCategoryInfo(BaseModel):
    """??????"""
    key: str
    name: str
    count: int
