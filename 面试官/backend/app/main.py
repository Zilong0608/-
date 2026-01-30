# -*- coding: utf-8 -*-
"""
主应用入口
"""

import os
import yaml
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .api import router, set_engine
from .core.interview_engine import InterviewEngine
from .core.personality_manager import PersonalityManager
from .core.evaluation_engine import EvaluationEngine
from .services.question_service import QuestionRepository, JsonQuestionRepository, SupabaseQuestionRepository
from .services.data_service import DataService
from .services.ai_service import AIService
from .utils.logger import setup_logger, get_logger
from .models import DifficultyLevel

# 加载环境变量
load_dotenv()

logger = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global logger

    if logger is None:
        logger = get_logger("main")

    # 启动时初始化
    logger.info("Starting Interview System...")

    # 初始化所有组件
    try:
        engine = initialize_engine()
        set_engine(engine)
        logger.info("Interview engine initialized successfully")

        # 测试连接（可通过环境变量跳过）
        skip_tests = str(os.getenv("SKIP_STARTUP_TESTS", "0")).strip().lower() in {"1", "true", "yes", "y"}
        if skip_tests:
            logger.info("Startup connection tests skipped (SKIP_STARTUP_TESTS=1)")
        else:
            if engine.question_repo.test_connection():
                logger.info("RAG connection test passed")
            else:
                logger.warning("RAG connection test failed")

            if engine.ai_service.test_connection():
                logger.info("AI service connection test passed")
            else:
                logger.warning("AI service connection test failed")

    except Exception as e:
        logger.error(f"Failed to initialize engine: {e}")
        raise

    yield

    # 关闭时清理
    logger.info("Shutting down Interview System...")


def initialize_engine() -> InterviewEngine:
    """
    初始化面试引擎及所有依赖组件

    Returns:
        InterviewEngine 实例
    """
    global logger

    # 1. 加载配置
    config_path = Path(__file__).parent / "config" / "settings.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 2. 初始化日志
    log_config = config.get('logging', {})
    logger = setup_logger(
        log_file=log_config.get('file'),
        log_level=log_config.get('level', 'INFO')
    )

    logger.info("Initializing Interview System components...")

    # 3. 初始化 AI 服务
    ai_config = config['ai']
    ai_service = AIService(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=ai_config['model'],
        max_retries=ai_config['max_retries'],
        timeout=ai_config['timeout']
    )

    # 4. 初始化问题仓库 (JSON or RAG)
    rag_config = config['rag']
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
    supabase_table = os.getenv('SUPABASE_TABLE', 'interview_questions')
    json_path = os.getenv('QUESTION_JSON_PATH')

    if supabase_url and supabase_key:
        question_repo = SupabaseQuestionRepository(
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            table_name=supabase_table,
            preload_count=rag_config['preload_count'],
            refill_threshold=rag_config['refill_threshold']
        )
        logger.info(f"Using Supabase question source: {supabase_url}")
    elif json_path:
        question_repo = JsonQuestionRepository(
            json_path=json_path,
            preload_count=rag_config['preload_count'],
            refill_threshold=rag_config['refill_threshold']
        )
        logger.info(f"Using JSON question source: {json_path}")
    else:
        question_repo = QuestionRepository(
            vector_store_path=os.getenv('RAG_VECTOR_STORE_PATH', '../数据/data_index'),
            preload_count=rag_config['preload_count'],
            refill_threshold=rag_config['refill_threshold']
        )

    # 5. 初始化数据服务
    db_type = os.getenv('DATABASE_TYPE', 'sqlite')
    if db_type == 'sqlite':
        db_path = os.getenv('SQLITE_DB_PATH', '../data/interviews.db')
    else:
        # PostgreSQL 支持留待后续
        raise NotImplementedError("PostgreSQL not yet supported")

    data_service = DataService(db_path=db_path)

    # 6. 初始化人格管理器
    personalities_dir = Path(__file__).parent / "config" / "personalities"
    personality_manager = PersonalityManager(str(personalities_dir))

    # 7. 初始化评估引擎
    interview_config = config['interview']
    followup_config = interview_config.get('followup', {})
    score_threshold = followup_config.get('score_threshold')
    if isinstance(score_threshold, (list, tuple)) and len(score_threshold) == 2:
        followup_score_threshold = (float(score_threshold[0]), float(score_threshold[1]))
    else:
        followup_score_threshold = (
            float(interview_config.get('followup_score_min', 6.0)),
            float(interview_config.get('followup_score_max', 8.0))
        )
    evaluation_engine = EvaluationEngine(
        ai_service=ai_service,
        personality_manager=personality_manager,
        followup_score_threshold=followup_score_threshold
    )

    # 8. 创建面试引擎
    engine = InterviewEngine(
        question_repo=question_repo,
        data_service=data_service,
        personality_manager=personality_manager,
        evaluation_engine=evaluation_engine,
        ai_service=ai_service
    )

    logger.info("All components initialized successfully")
    return engine


# 创建 FastAPI 应用
app = FastAPI(
    title="AI Interview System",
    description="智能面试官系统 - 基于 RAG 和多人格的面试评估系统",
    version="1.0.0",
    lifespan=lifespan
)

# 配置 CORS（用于前端对接）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)

# 挂载 Web UI
ui_dir = Path(__file__).parent / "web_ui"
if ui_dir.exists():
    app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="ui")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "AI Interview System API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

