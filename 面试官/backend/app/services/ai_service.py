# -*- coding: utf-8 -*-
"""
AI 服务 - OpenAI API 封装
"""

import io
import json
import time
from typing import Dict, Optional

from openai import OpenAI
from openai import OpenAIError, RateLimitError, APITimeoutError

from ..utils.logger import get_logger
from ..utils.exceptions import AIServiceException

logger = get_logger("ai_service")


class AIService:
    """
    AI 服务 - 封装所有 OpenAI API 调用
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        初始化

        Args:
            api_key: OpenAI API Key
            model: 使用的模型
            max_retries: 最大重试次数
            timeout: 超时时间（秒）
        """
        self.client = OpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

        logger.info(f"AIService initialized with model: {model}")

    def evaluate_answer(
        self,
        prompt: str,
        temperature: float = 0.3
    ) -> Dict:
        """
        调用 GPT 评估答案

        Args:
            prompt: 评估 prompt
            temperature: 温度参数（评估要稳定，温度低）

        Returns:
            评估结果（JSON格式）

        Raises:
            AIServiceException: AI服务调用失败
        """
        logger.debug("Calling AI to evaluate answer")

        try:
            response = self._call_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    response_format={"type": "json_object"}
                )
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            logger.debug("Answer evaluation completed successfully")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            raise AIServiceException(
                "AI returned invalid JSON response",
                original_error=e
            )
        except Exception as e:
            logger.error(f"AI evaluation failed: {e}")
            raise AIServiceException(
                "Failed to evaluate answer",
                original_error=e
            )

    def generate_followup(
        self,
        prompt: str,
        temperature: float = 0.7
    ) -> str:
        """
        生成追问

        Args:
            prompt: 追问 prompt
            temperature: 温度参数（追问可以有创意）

        Returns:
            追问内容

        Raises:
            AIServiceException: AI服务调用失败
        """
        logger.debug("Calling AI to generate follow-up question")

        try:
            response = self._call_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature
                )
            )

            followup = response.choices[0].message.content.strip()
            logger.debug(f"Follow-up question generated: {followup[:50]}...")
            return followup

        except Exception as e:
            logger.error(f"Failed to generate follow-up: {e}")
            raise AIServiceException(
                "Failed to generate follow-up question",
                original_error=e
            )

    def generate_report(
        self,
        prompt: str,
        temperature: float = 0.5
    ) -> Dict:
        """
        生成面试报告

        Args:
            prompt: 报告生成 prompt
            temperature: 温度参数

        Returns:
            报告内容（JSON格式）

        Raises:
            AIServiceException: AI服务调用失败
        """
        logger.debug("Calling AI to generate final report")

        try:
            response = self._call_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    response_format={"type": "json_object"}
                )
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            logger.debug("Final report generated successfully")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse report JSON: {e}")
            raise AIServiceException(
                "AI returned invalid JSON for report",
                original_error=e
            )
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            raise AIServiceException(
                "Failed to generate final report",
                original_error=e
            )

    def text_to_speech(
        self,
        text: str,
        model: str = "gpt-4o-mini-tts-2025-12-15",
        voice: str = "alloy",
        response_format: str = "wav",
        speed: Optional[float] = None
    ) -> bytes:
        """
        文本转语音

        Args:
            text: 需要朗读的文本
            model: TTS 模型
            voice: 声音
            response_format: 输出格式
            speed: 语速（可选）

        Returns:
            音频字节
        """
        if not text:
            return b""

        def _call():
            payload = {
                "model": model,
                "voice": voice,
                "input": text,
                "response_format": response_format
            }
            if speed is not None:
                payload["speed"] = speed
            return self.client.audio.speech.create(**payload)

        try:
            response = self._call_with_retry(_call)
            if hasattr(response, "read"):
                return response.read()
            if hasattr(response, "content"):
                return response.content
            if isinstance(response, (bytes, bytearray)):
                return bytes(response)
            return b""
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            raise AIServiceException(
                "Failed to synthesize speech",
                original_error=e
            )

    def speech_to_text(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        model: str = "gpt-realtime-mini-2025-12-15",
        language: Optional[str] = "zh"
    ) -> str:
        """
        è¯­éŸ³è½¬æ–‡å­—
        """
        if not audio_bytes:
            return ""

        def _call():
            buf = io.BytesIO(audio_bytes)
            buf.name = filename or "audio.webm"
            payload = {
                "model": model,
                "file": buf
            }
            if language:
                payload["language"] = language
            return self.client.audio.transcriptions.create(**payload)

        try:
            response = self._call_with_retry(_call)
            if hasattr(response, "text"):
                return response.text or ""
            if isinstance(response, dict):
                return response.get("text", "") or ""
            return ""
        except Exception as e:
            logger.error(f"STT failed: {e}")
            raise AIServiceException(
                "Failed to transcribe audio",
                original_error=e
            )

    def _call_with_retry(self, func, backoff: float = 2.0):
        """
        带重试的 API 调用

        Args:
            func: 要调用的函数
            backoff: 退避倍数

        Returns:
            API 响应

        Raises:
            AIServiceException: 重试失败
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return func()

            except RateLimitError as e:
                last_exception = e
                wait_time = backoff ** attempt
                logger.warning(
                    f"Rate limit hit, retrying in {wait_time}s "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(wait_time)

            except APITimeoutError as e:
                last_exception = e
                logger.warning(
                    f"API timeout, retrying "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(backoff ** attempt)

            except OpenAIError as e:
                # 其他 OpenAI 错误，直接抛出
                logger.error(f"OpenAI API error: {e}")
                raise AIServiceException(str(e), original_error=e)

            except Exception as e:
                # 未知错误，直接抛出
                logger.error(f"Unexpected error in AI call: {e}")
                raise AIServiceException(
                    "Unexpected error during AI call",
                    original_error=e
                )

        # 所有重试都失败
        logger.error(f"All {self.max_retries} retries failed")
        raise AIServiceException(
            f"Failed after {self.max_retries} retries",
            original_error=last_exception
        )

    def test_connection(self) -> bool:
        """
        测试 AI 服务连接

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            logger.info("AI service connection test successful")
            return True

        except Exception as e:
            logger.error(f"AI service connection test failed: {e}")
            return False
