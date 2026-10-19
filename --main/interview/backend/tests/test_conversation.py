import unittest
from pathlib import Path
from unittest.mock import Mock
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from loguru import logger

logger.disable("app")

from app.core.evaluation_engine import EvaluationEngine
from app.core.interview_engine import InterviewEngine
from app.core.personality_manager import PersonalityManager
from app.models import Question, QuestionType, DifficultyLevel, InterviewSession, InterviewConfig, InterviewStatus
from app.utils.exceptions import InvalidParameterException


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.ai = Mock()
        self.personalities = PersonalityManager(str(Path(__file__).resolve().parents[1] / "app/config/personalities"))
        self.persona = self.personalities.get_random_personality()
        self.evaluator = EvaluationEngine(self.ai, self.personalities)
        self.question = Question("q1", "How do you prevent stale cache reads?", "Discuss invalidation and consistency.", QuestionType.SCENARIO, DifficultyLevel.INTERMEDIATE, [], "backend")
        self.payload = dict(technical_accuracy=9, clarity=8, depth_breadth=9, keywords_hit=["invalidation"], keywords_missed=[], weaknesses=[], suggestions=[], feedback="You explained invalidation; let's examine a concurrent write.", needs_followup=True, followup_question="What happens if the write and invalidation race?")
        self.ai.evaluate_answer.return_value = self.payload
        self.engine = InterviewEngine(Mock(), Mock(), self.personalities, self.evaluator, self.ai)
        self.session = InterviewSession("s1", InterviewConfig("backend", DifficultyLevel.INTERMEDIATE, 30), self.persona, status=InterviewStatus.IN_PROGRESS, current_question=self.question, asked_question_ids=["q1"])
        self.engine.active_sessions["s1"] = self.session

    def test_content_based_followup_outside_old_score_band(self):
        result = self.engine.submit_answer("s1", "I invalidate the cache after writes.")
        self.assertTrue(result["has_followup"])
        self.assertEqual(result["feedback"], self.payload["feedback"])
        self.ai.generate_followup.assert_not_called()
        self.ai.translate_to_chinese.assert_not_called()

    def test_followup_has_context_and_cannot_recurse(self):
        self.engine.submit_answer("s1", "I invalidate the cache after writes.")
        result = self.engine.submit_answer("s1", "I use versioned keys to prevent stale writes.")
        self.assertFalse(result["has_followup"])
        self.assertTrue(self.session.answer_records[-1].is_followup)
        self.assertEqual(self.session.answer_records[-1].parent_question_id, "q1")
        prompt = self.ai.evaluate_answer.call_args.args[0]
        self.assertIn("I invalidate the cache after writes.", prompt)
        self.assertEqual(len(self.session.asked_question_ids), 1)

    def test_no_followup_when_model_says_move_on(self):
        self.payload.update(technical_accuracy=7, needs_followup=False)
        self.assertFalse(self.engine.submit_answer("s1", "I don't know; please skip.")["has_followup"])

    def test_missing_reference_does_not_invent_a_grading_key(self):
        self.question.reference_answer = ""
        self.engine.submit_answer("s1", "Use versioned cache keys.")
        self.ai.generate_reference_answer.assert_not_called()
        self.assertEqual(self.question.reference_answer, "")

    def test_question_selection_skips_extraction_fragments(self):
        self.engine.question_repo.get_next_question.side_effect = [
            replace(self.question, question_id="bad1", content="构建优化问题：？"),
            replace(self.question, question_id="bad2", content="不足点2：训练过程较长？"),
            replace(self.question, question_id="good", content="如何减少模型训练时间？")
        ]
        question = self.engine._get_next_question_internal(self.session)
        self.assertEqual(question.question_id, "good")
        self.assertEqual(self.session.asked_question_ids, ["q1"])

    def test_disabled_followups_are_respected(self):
        self.session.config.enable_followup = False
        self.assertFalse(self.engine.submit_answer("s1", "Use invalidation.")["has_followup"])

    def test_blank_and_duplicate_answers_are_rejected(self):
        with self.assertRaises(InvalidParameterException):
            self.engine.submit_answer("s1", "   ")
        self.payload.update(needs_followup=False)
        self.engine.submit_answer("s1", "Use invalidation.")
        with self.assertRaises(InvalidParameterException):
            self.engine.submit_answer("s1", "Use invalidation again.")
        self.assertEqual(len(self.session.answer_records), 1)

    def test_unavailable_evaluation_keeps_turn_retryable(self):
        self.ai.evaluate_answer.side_effect = RuntimeError("offline")
        with self.assertRaises(InvalidParameterException):
            self.engine.submit_answer("s1", "Use invalidation.")
        self.assertEqual(self.session.answer_records, [])
        self.engine.data_service.save_answer_record.assert_not_called()

    def test_nonfinite_score_is_not_accepted(self):
        self.payload["technical_accuracy"] = float("nan")
        result = self.evaluator.evaluate_answer(self.question, "answer", self.persona, "backend")
        self.assertFalse(result.needs_followup)
        self.assertEqual(result.weaknesses, ["AI evaluation unavailable"])

    def test_concurrent_submissions_do_not_duplicate_records(self):
        entered, release = Event(), Event()
        def evaluate(_prompt):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test timed out")
            return self.payload
        self.ai.evaluate_answer.side_effect = evaluate
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.engine.submit_answer, "s1", "Use invalidation.")
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(InvalidParameterException):
                    self.engine.submit_answer("s1", "Duplicate click.")
            finally:
                release.set()
            pending.result(timeout=5)
        self.assertEqual(len(self.session.answer_records), 1)

    def test_report_includes_candidate_evidence(self):
        self.payload.update(needs_followup=False)
        self.engine.submit_answer("s1", "I invalidate the cache after writes.")
        evaluation = self.engine.data_service.save_evaluation.call_args.args[2]
        details = self.engine._build_answer_details(self.session.answer_records, {"q1": evaluation})
        self.assertIn("I invalidate the cache after writes.", details)
        self.assertIn("How do you prevent stale cache reads?", details)


if __name__ == "__main__":
    unittest.main()
