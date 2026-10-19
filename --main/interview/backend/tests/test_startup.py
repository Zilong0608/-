import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from app.services import question_factory as factory
from app.utils.exceptions import ConfigurationException, RAGConnectionException


class QuestionSourceTests(unittest.TestCase):
    config = {"preload_count": 100, "refill_threshold": 20}

    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_default_uses_shipped_bank_without_network(self):
        with patch.object(factory, "SupabaseQuestionRepository") as cloud:
            repo = factory.create_question_repository(self.config)
        self.assertTrue(repo.test_connection())
        self.assertTrue(repo.list_categories())
        cloud.assert_not_called()

    def test_explicit_json_takes_priority_over_stale_cloud_settings(self):
        os.environ.update(QUESTION_JSON_PATH="../../data/test.json", SUPABASE_URL="https://invalid.invalid", SUPABASE_SERVICE_KEY="test")
        with patch.object(factory, "JsonQuestionRepository") as local, patch.object(factory, "SupabaseQuestionRepository") as cloud:
            factory.create_question_repository(self.config)
        self.assertEqual(Path(local.call_args.kwargs["json_path"]), (factory.BACKEND_DIR / "../../data/test.json").resolve())
        cloud.assert_not_called()

    def test_dns_failure_falls_back_to_real_bundled_bank(self):
        os.environ.update(SUPABASE_URL="https://missing.invalid", SUPABASE_SERVICE_KEY="test")
        with patch.object(factory, "SupabaseQuestionRepository", side_effect=httpx.ConnectError("[Errno -2] Name or service not known")):
            repo = factory.create_question_repository(self.config)
        self.assertTrue(repo.test_connection())

    def test_authentication_errors_are_not_hidden(self):
        os.environ.update(SUPABASE_URL="https://project.supabase.co", SUPABASE_SERVICE_KEY="test")
        with patch.object(factory, "SupabaseQuestionRepository", side_effect=RAGConnectionException("HTTP 401")):
            with self.assertRaises(RAGConnectionException):
                factory.create_question_repository(self.config)

    def test_placeholder_url_is_actionable_and_never_requested(self):
        os.environ.update(SUPABASE_URL="https://your-project.supabase.co", SUPABASE_SERVICE_KEY="test")
        with patch.object(factory, "SupabaseQuestionRepository") as cloud:
            with self.assertRaisesRegex(ConfigurationException, "SUPABASE_URL"):
                factory.create_question_repository(self.config)
        cloud.assert_not_called()

    def test_explicit_vector_source_is_preserved(self):
        os.environ["RAG_VECTOR_STORE_PATH"] = "custom-index"
        with patch.object(factory, "QuestionRepository") as vector:
            factory.create_question_repository(self.config)
        self.assertEqual(vector.call_args.kwargs["vector_store_path"], "custom-index")

    def test_dns_failure_and_missing_fallback_explains_configuration(self):
        os.environ.update(SUPABASE_URL="https://missing.invalid", SUPABASE_SERVICE_KEY="test")
        with patch.object(factory, "SupabaseQuestionRepository", side_effect=httpx.ConnectError("DNS failed")), patch.object(factory, "BUNDLED_QUESTIONS", Path("does-not-exist.json")):
            with self.assertRaisesRegex(ConfigurationException, "SUPABASE_URL/DNS"):
                factory.create_question_repository(self.config)

    def test_app_starts_and_serves_healthz_during_supabase_dns_outage(self):
        from app.main import app

        with tempfile.TemporaryDirectory() as temp:
            os.environ.update(
                SUPABASE_URL="https://missing.invalid", SUPABASE_SERVICE_KEY="test",
                SQLITE_DB_PATH=str(Path(temp) / "interviews.db"),
            )
            with patch.object(factory, "SupabaseQuestionRepository", side_effect=httpx.ConnectError("DNS failed")), patch("app.main.AIService") as ai:
                with TestClient(app) as client:
                    self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
                    self.assertEqual(client.get("/").status_code, 200)
                ai.return_value.test_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
