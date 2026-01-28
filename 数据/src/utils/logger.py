# -*- coding: utf-8 -*-
"""
日志模块
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logger(
    name: str = "rag_pipeline",
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
    console_output: bool = True
) -> logging.Logger:
    """
    设置日志器

    Args:
        name: 日志器名称
        log_dir: 日志文件目录
        level: 日志级别
        console_output: 是否输出到控制台

    Returns:
        配置好的日志器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 清除已有的处理器
    logger.handlers.clear()

    # 日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台输出
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件输出
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{name}_{timestamp}.log"

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 全局日志器缓存
_loggers = {}


def get_logger(name: str = "rag_pipeline") -> logging.Logger:
    """
    获取日志器（如果不存在则创建默认配置的日志器）

    Args:
        name: 日志器名称

    Returns:
        日志器实例
    """
    if name not in _loggers:
        _loggers[name] = setup_logger(name)
    return _loggers[name]
