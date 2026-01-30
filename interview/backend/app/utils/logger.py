# -*- coding: utf-8 -*-
"""
日志工具
"""

import sys
from pathlib import Path
from loguru import logger
from typing import Optional


def setup_logger(
    log_file: Optional[str] = None,
    log_level: str = "INFO",
    rotation: str = "1 day",
    retention: str = "30 days"
):
    """
    配置全局日志

    Args:
        log_file: 日志文件路径
        log_level: 日志级别
        rotation: 日志轮转策略
        retention: 日志保留时间
    """
    # 移除默认handler
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True
    )

    # 添加文件输出（如果指定）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation=rotation,
            retention=retention,
            encoding="utf-8"
        )

    return logger


def get_logger(name: str):
    """
    获取带名称的logger

    Args:
        name: 模块名称

    Returns:
        logger实例
    """
    return logger.bind(name=name)
