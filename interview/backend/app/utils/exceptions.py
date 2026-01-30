# -*- coding: utf-8 -*-
"""
自定义异常类
"""


class InterviewException(Exception):
    """面试系统基础异常"""
    pass


class SessionNotFoundException(InterviewException):
    """会话不存在异常"""
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Interview session not found: {session_id}")


class QuestionPoolEmptyException(InterviewException):
    """题库为空异常"""
    def __init__(self, message: str = "Question pool is empty"):
        super().__init__(message)


class AIServiceException(InterviewException):
    """AI服务异常"""
    def __init__(self, message: str, original_error: Exception = None):
        self.original_error = original_error
        super().__init__(f"AI Service Error: {message}")


class RAGConnectionException(InterviewException):
    """RAG连接异常"""
    def __init__(self, message: str = "Failed to connect to RAG vector store"):
        super().__init__(message)


class ConfigurationException(InterviewException):
    """配置异常"""
    def __init__(self, message: str):
        super().__init__(f"Configuration Error: {message}")


class InvalidParameterException(InterviewException):
    """无效参数异常"""
    def __init__(self, param_name: str, reason: str):
        super().__init__(f"Invalid parameter '{param_name}': {reason}")
