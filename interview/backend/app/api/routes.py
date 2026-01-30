# -*- coding: utf-8 -*-
"""
API 路由
"""

import asyncio
import json
import os

from fastapi import (
    APIRouter,
    HTTPException,
    status,
    BackgroundTasks,
    UploadFile,
    File,
    Form,
    WebSocket,
    WebSocketDisconnect
)
from fastapi.responses import Response
from typing import List, Optional, Dict
import websockets

from .schemas import (
    CreateSessionRequest, SessionResponse, StartInterviewResponse,
    SubmitAnswerRequest, SubmitAnswerResponse, NextQuestionResponse,
    InterviewReportResponse, PersonalityInfo, StatisticsResponse,
    HealthResponse, ErrorResponse, EvaluationResponse, TTSRequest,
    AsyncAnswerResponse, EvaluationLookupResponse, STTResponse,
    QuestionCategoryInfo
)
from ..core.interview_engine import InterviewEngine
from ..models import DifficultyLevel
from ..utils.logger import get_logger
from ..utils.exceptions import (
    SessionNotFoundException, QuestionPoolEmptyException,
    InvalidParameterException, InterviewException
)

logger = get_logger("api")

# 创建路由器
router = APIRouter(prefix="/api/v1", tags=["interview"])

# 全局引擎实例（将在 main.py 中注入）
_engine: InterviewEngine = None


def set_engine(engine: InterviewEngine):
    """设置引擎实例"""
    global _engine
    _engine = engine
    logger.info("Interview engine set for API routes")


def get_engine() -> InterviewEngine:
    """获取引擎实例"""
    if _engine is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interview engine not initialized"
        )
    return _engine

def _build_report_details(engine: InterviewEngine, session_id: str, job_type: str) -> List[Dict]:
    records = engine.data_service.get_answer_records(session_id)
    evaluations = engine.data_service.get_evaluations(session_id)
    eval_map: Dict[str, Dict] = {}
    for item in evaluations:
        eval_map[item.get("question_id")] = item
    llm_cache: Dict[str, str] = {}

    details: List[Dict] = []
    for record in records:
        question_id = record.get("question_id")
        question = (record.get("question_content") or "").strip()
        user_answer = (record.get("user_answer") or "").strip()
        eval_data = eval_map.get(question_id, {})
        llm_answer = (record.get("reference_answer") or "").strip()
        if not llm_answer and question:
            try:
                llm_answer = llm_cache.get(question)
                if not llm_answer:
                    llm_answer = engine.ai_service.generate_reference_answer(question, job_type=job_type)
                    llm_cache[question] = llm_answer
            except Exception:
                llm_answer = ""

        details.append({
            "question_id": question_id,
            "question": question,
            "user_answer": user_answer,
            "is_followup": bool(record.get("is_followup")),
            "parent_question_id": record.get("parent_question_id"),
            "total_score": float(eval_data.get("total_score", 0.0)),
            "technical_accuracy": float(eval_data.get("technical_accuracy", 0.0)),
            "clarity": float(eval_data.get("clarity", 0.0)),
            "depth_breadth": float(eval_data.get("depth_breadth", 0.0)),
            "weaknesses": eval_data.get("weaknesses", []),
            "suggestions": eval_data.get("suggestions", []),
            "llm_answer": llm_answer
        })

    return details



# ============ 会话管理 ============

@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: CreateSessionRequest):
    """
    创建面试会话
    """
    try:
        engine = get_engine()

        # 解析难度
        try:
            difficulty_value = request.difficulty
            difficulty_map = {
                "easy": DifficultyLevel.BASIC,
                "medium": DifficultyLevel.INTERMEDIATE,
                "hard": DifficultyLevel.ADVANCED
            }
            if difficulty_value in difficulty_map:
                difficulty = difficulty_map[difficulty_value]
            else:
                difficulty = DifficultyLevel(difficulty_value)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid difficulty: {request.difficulty}. "
                    "Must be 基础/进阶/高级 or easy/medium/hard"
                )
            )

        # 创建会话
        session = engine.create_session(
            job_type=request.job_type,
            difficulty=difficulty,
            max_questions=request.max_questions,
            personality_name=request.personality_name,
            question_category=request.question_category
        )

        # 返回会话信息
        status_info = engine.get_session_status(session.session_id)

        return SessionResponse(
            session_id=status_info['session_id'],
            status=status_info['status'],
            personality=status_info['personality'],
            job_type=status_info['job_type'],
            difficulty=status_info['difficulty'],
            question_category=status_info.get('question_category'),
            questions_answered=status_info['questions_answered'],
            max_questions=status_info['max_questions'],
            start_time=status_info['start_time'],
            end_time=status_info['end_time']
        )

    except InvalidParameterException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )


@router.post("/sessions/{session_id}/start", response_model=StartInterviewResponse)
async def start_interview(session_id: str):
    """
    启动面试
    """
    try:
        engine = get_engine()

        opening, first_question = engine.start_interview(session_id)

        return StartInterviewResponse(
            session_id=session_id,
            opening=opening,
            first_question=first_question
        )

    except SessionNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except QuestionPoolEmptyException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except InvalidParameterException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to start interview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start interview"
        )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_status(session_id: str):
    """
    获取会话状态
    """
    try:
        engine = get_engine()
        status_info = engine.get_session_status(session_id)

        return SessionResponse(
            session_id=status_info['session_id'],
            status=status_info['status'],
            personality=status_info['personality'],
            job_type=status_info['job_type'],
            difficulty=status_info['difficulty'],
            question_category=status_info.get('question_category'),
            questions_answered=status_info['questions_answered'],
            max_questions=status_info['max_questions'],
            start_time=status_info['start_time'],
            end_time=status_info['end_time']
        )

    except SessionNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session status"
        )


# ============ 答题流程 ============

@router.post("/sessions/{session_id}/answer", response_model=SubmitAnswerResponse)
async def submit_answer(session_id: str, request: SubmitAnswerRequest):
    """
    提交答案
    """
    try:
        engine = get_engine()
        result = engine.submit_answer(session_id, request.answer)

        return SubmitAnswerResponse(
            evaluation=EvaluationResponse(**result['evaluation']),
            feedback=result['feedback'],
            has_followup=result['has_followup'],
            followup_question=result.get('followup_question')
        )

    except SessionNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidParameterException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to submit answer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit answer"
        )


@router.post("/sessions/{session_id}/answer-async", response_model=AsyncAnswerResponse)
async def submit_answer_async(
    session_id: str,
    request: SubmitAnswerRequest,
    background_tasks: BackgroundTasks
):
    """
    å¼‚æ­¥æäº¤ç­”æ¡ˆ
    """
    try:
        engine = get_engine()
        result = engine.submit_answer_async(session_id, request.answer)
        queued = bool(result.get("should_evaluate"))
        if queued:
            background_tasks.add_task(
                engine.evaluate_answer_async,
                session_id,
                result["question"],
                request.answer,
                result["personality"],
                result["job_type"]
            )

        return AsyncAnswerResponse(
            queued=queued,
            question_id=result["question"].question_id
        )

    except SessionNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidParameterException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to submit answer async: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit answer"
        )


@router.post("/sessions/{session_id}/followup-answer")
async def submit_followup_answer(session_id: str, request: SubmitAnswerRequest):
    """
    提交追问答案
    """
    try:
        engine = get_engine()
        result = engine.submit_followup_answer(session_id, request.answer)

        return result

    except SessionNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidParameterException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to submit followup answer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit followup answer"
        )


@router.get("/sessions/{session_id}/next-question", response_model=NextQuestionResponse)
async def get_next_question(session_id: str):
    """
    获取下一题
    """
    try:
        engine = get_engine()

        # 获取会话状态
        status_info = engine.get_session_status(session_id)

        # 获取下一题
        next_question = engine.get_next_question(session_id)

        return NextQuestionResponse(
            has_next=next_question is not None,
            question=next_question,
            questions_answered=status_info['questions_answered'],
            max_questions=status_info['max_questions']
        )

    except SessionNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidParameterException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get next question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get next question"
        )


# ============ 报告生成 ============

@router.get(
    "/sessions/{session_id}/evaluations/{question_id}",
    response_model=EvaluationLookupResponse
)
async def get_evaluation(session_id: str, question_id: str):
    """
    获取指定题目的评估
    """
    try:
        engine = get_engine()
        evaluation = engine.data_service.get_evaluation(session_id, question_id)
        if not evaluation:
            return EvaluationLookupResponse(
                question_id=question_id,
                has_evaluation=False,
                evaluation=None
            )

        eval_response = EvaluationResponse(
            total_score=evaluation["total_score"],
            technical_accuracy=evaluation["technical_accuracy"],
            clarity=evaluation["clarity"],
            depth_breadth=evaluation["depth_breadth"],
            keyword_coverage=evaluation["keyword_coverage"],
            weaknesses=evaluation["weaknesses"],
            suggestions=evaluation["suggestions"]
        )
        return EvaluationLookupResponse(
            question_id=question_id,
            has_evaluation=True,
            evaluation=eval_response
        )

    except Exception as e:
        logger.error(f"Failed to get evaluation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get evaluation"
        )


@router.post("/sessions/{session_id}/end", response_model=InterviewReportResponse)
async def end_interview(session_id: str):
    """
    结束面试并生成报告
    """
    try:
        engine = get_engine()
        report = engine.end_interview(session_id)
        details = _build_report_details(engine, session_id, report.job_type)

        return InterviewReportResponse(
            session_id=session_id,
            overall_score=report.overall_score,
            avg_technical_accuracy=report.avg_technical_accuracy,
            avg_clarity=report.avg_clarity,
            avg_depth_breadth=report.avg_depth_breadth,
            correct_rate=report.correct_rate,
            weak_areas=report.weak_areas,
            strong_areas=report.strong_areas,
            suggestions=report.suggestions,
            details=details
        )

    except SessionNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to end interview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to end interview"
        )


@router.get("/sessions/{session_id}/report", response_model=InterviewReportResponse)
async def get_report(session_id: str):
    """
    获取已生成的报告
    """
    try:
        engine = get_engine()
        report_data = engine.data_service.get_report(session_id)

        if not report_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found for this session"
            )

        return InterviewReportResponse(
            session_id=session_id,
            overall_score=report_data['overall_score'],
            avg_technical_accuracy=report_data['avg_technical_accuracy'],
            avg_clarity=report_data['avg_clarity'],
            avg_depth_breadth=report_data['avg_depth_breadth'],
            correct_rate=report_data['correct_rate'],
            weak_areas=report_data['weak_areas'],
            strong_areas=report_data['strong_areas'],
            suggestions=report_data['suggestions']
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get report"
        )


# ============ 信息查询 ============

@router.get("/personalities", response_model=List[PersonalityInfo])
async def list_personalities():
    """
    列出所有可用的人格
    """
    try:
        engine = get_engine()
        names = engine.personality_manager.get_all_personality_names()

        personalities = []
        for name in names:
            personality = engine.personality_manager.get_personality_by_name(name)
            if personality:
                personalities.append(PersonalityInfo(
                    name=personality.name,
                    description=personality.description
                ))

        return personalities

    except Exception as e:
        logger.error(f"Failed to list personalities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list personalities"
        )



@router.get("/question-categories", response_model=List[QuestionCategoryInfo])
async def list_question_categories():
    """
    ??????????????????
    """
    try:
        engine = get_engine()
        repo = engine.question_repo
        if hasattr(repo, "list_categories"):
            categories = repo.list_categories()
            return [QuestionCategoryInfo(**item) for item in categories]
        return []

    except Exception as e:
        logger.error(f"Failed to list question categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list question categories"
        )

@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics():
    """
    获取统计数据
    """
    try:
        engine = get_engine()
        stats = engine.data_service.get_statistics()

        return StatisticsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics"
        )


# ============ 健康检查 ============

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查
    """
    try:
        engine = get_engine()

        # 检查 RAG 连接
        rag_connected = engine.question_repo.test_connection()

        # 检查 AI 连接
        ai_connected = engine.ai_service.test_connection()

        return HealthResponse(
            status="healthy" if (rag_connected and ai_connected) else "degraded",
            rag_connected=rag_connected,
            ai_connected=ai_connected
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            rag_connected=False,
            ai_connected=False
        )


# ============ TTS ============

@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    文本转语音
    """
    try:
        engine = get_engine()
        model = (request.model or "gpt-4o-mini-tts-2025-12-15").strip()
        voice = (request.voice or "alloy").strip()
        fmt = (request.format or "mp3").strip().lower()
        speed = request.speed
        if fmt not in {"mp3", "wav"}:
            fmt = "mp3"

        audio_bytes = engine.ai_service.text_to_speech(
            text=request.text,
            model=model,
            voice=voice,
            response_format=fmt,
            speed=speed
        )
        media_type = "audio/wav" if fmt == "wav" else "audio/mpeg"
        return Response(content=audio_bytes, media_type=media_type)

    except Exception as e:
        logger.error(f"TTS failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate speech"
        )


@router.post("/stt", response_model=STTResponse)
async def speech_to_text(
    file: UploadFile = File(...),
    model: Optional[str] = Form(None),
    language: Optional[str] = Form(None)
):
    """
    è¯­éŸ³è½¬æ–‡å­—
    """
    try:
        engine = get_engine()
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty audio file"
            )

        logger.info(f"STT request: filename={file.filename}, model={model or 'gpt-realtime-mini-2025-12-15'}")
        text = engine.ai_service.speech_to_text(
            audio_bytes=audio_bytes,
            filename=file.filename or "audio.webm",
            model=(model or "gpt-realtime-mini-2025-12-15").strip(),
            language=(language or "zh").strip() if language is not None else "zh"
        )
        logger.info(f"STT done: {len(text)} chars")
        return STTResponse(text=text)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"STT failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transcribe audio"
        )


# ============ Realtime STT ============

@router.websocket("/ws/realtime-stt")
async def realtime_stt(websocket: WebSocket):
    """
    Realtime 语音转写（WebSocket 代理）
    """
    await websocket.accept()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "OPENAI_API_KEY not set"
        }))
        await websocket.close(code=1011)
        return

    model = (websocket.query_params.get("model") or "gpt-realtime-mini-2025-12-15").strip()
    language = (websocket.query_params.get("language") or "zh").strip()
    realtime_url = f"wss://api.openai.com/v1/realtime?model={model}"

    try:
        async with websockets.connect(
            realtime_url,
            extra_headers={
                "Authorization": f"Bearer {api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "input_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1",
                        "language": language
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.3,
                        "prefix_padding_ms": 500,
                        "silence_duration_ms": 800
                    }
                }
            }
            await openai_ws.send(json.dumps(session_update))
            await websocket.send_text(json.dumps({
                "type": "status",
                "message": "realtime_connected"
            }))

            async def client_to_openai():
                try:
                    while True:
                        raw = await websocket.receive_text()
                        payload = json.loads(raw)
                        msg_type = payload.get("type")
                        if msg_type == "audio":
                            audio = payload.get("audio")
                            if audio:
                                await openai_ws.send(json.dumps({
                                    "type": "input_audio_buffer.append",
                                    "audio": audio
                                }))
                        elif msg_type == "stop":
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
                        elif msg_type == "close":
                            break
                except WebSocketDisconnect:
                    return

            async def openai_to_client():
                async for message in openai_ws:
                    try:
                        event = json.loads(message)
                    except Exception:
                        continue

                    event_type = event.get("type")
                    if event_type == "conversation.item.input_audio_transcription.completed":
                        transcript = (event.get("transcript") or "").strip()
                        if transcript:
                            await websocket.send_text(json.dumps({
                                "type": "transcript",
                                "text": transcript,
                                "final": True
                            }))
                    elif event_type == "conversation.item.input_audio_transcription.delta":
                        delta = (event.get("delta") or "").strip()
                        if delta:
                            await websocket.send_text(json.dumps({
                                "type": "transcript",
                                "text": delta,
                                "final": False
                            }))
                    elif event_type == "input_audio_buffer.speech_started":
                        await websocket.send_text(json.dumps({
                            "type": "status",
                            "message": "speech_started"
                        }))
                    elif event_type == "input_audio_buffer.speech_stopped":
                        await websocket.send_text(json.dumps({
                            "type": "status",
                            "message": "speech_stopped"
                        }))
                    elif event_type == "error":
                        err = event.get("error", {})
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": err.get("message", "Realtime error")
                        }))

            tasks = [
                asyncio.create_task(client_to_openai()),
                asyncio.create_task(openai_to_client())
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()

    except Exception as e:
        logger.error(f"Realtime STT failed: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Realtime connection failed"
            }))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
