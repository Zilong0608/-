"""Select a question source without making cloud DNS an availability dependency."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .question_service import (
    JsonQuestionRepository, QuestionRepository, SupabaseQuestionRepository,
)
from ..utils.exceptions import ConfigurationException
from ..utils.logger import get_logger

logger = get_logger("question_factory")
BACKEND_DIR = Path(__file__).resolve().parents[2]
BUNDLED_QUESTIONS = (
    Path(__file__).resolve().parents[4] / "data" / "第一轮仔细清洗"
    / "interview_questions_categorized.json"
)


def create_question_repository(rag_config):
    options = {
        "preload_count": rag_config["preload_count"],
        "refill_threshold": rag_config["refill_threshold"],
    }
    json_path = os.getenv("QUESTION_JSON_PATH", "").strip()
    if json_path:
        path = Path(json_path)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        logger.info("Using explicitly configured JSON question source")
        return JsonQuestionRepository(json_path=str(path.resolve()), **options)

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if supabase_url or supabase_key:
        if not (supabase_url and supabase_key):
            raise ConfigurationException("Set both SUPABASE_URL and SUPABASE_SERVICE_KEY, or use QUESTION_JSON_PATH")
        try:
            parsed = urlsplit(supabase_url)
            valid = (
                parsed.scheme in {"http", "https"} and parsed.hostname
                and not parsed.username and not parsed.password
                and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
                and parsed.hostname != "your-project.supabase.co"
            )
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationException(
                "SUPABASE_URL must be the actual project base URL (https://<project-ref>.supabase.co), "
                "without quotes, an API path, or placeholder values"
            )
        try:
            return SupabaseQuestionRepository(
                supabase_url=supabase_url,
                supabase_key=supabase_key,
                table_name=os.getenv("SUPABASE_TABLE", "interview_questions").strip(),
                **options,
            )
        except httpx.TransportError as exc:
            # Do not catch authentication, schema or empty-table errors here.
            if not BUNDLED_QUESTIONS.is_file():
                raise ConfigurationException(
                    "Supabase is unreachable and the bundled question bank is missing. "
                    "Check SUPABASE_URL/DNS or configure QUESTION_JSON_PATH."
                ) from exc
            logger.warning(
                "Supabase transport failed ({}); using the bundled JSON question bank. "
                "Check SUPABASE_URL and DNS in the deployment environment.",
                type(exc).__name__,
            )
            return JsonQuestionRepository(json_path=str(BUNDLED_QUESTIONS), **options)

    vector_path = os.getenv("RAG_VECTOR_STORE_PATH", "").strip()
    if vector_path:
        return QuestionRepository(vector_store_path=vector_path, **options)
    logger.info("Using the bundled JSON question bank")
    return JsonQuestionRepository(json_path=str(BUNDLED_QUESTIONS), **options)
