#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API 服务器启动脚本
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import uvicorn

if __name__ == "__main__":
    reload_enabled = str(os.getenv("UVICORN_RELOAD", "0")).strip().lower() in {"1", "true", "yes", "y"}
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload_enabled,
        log_level="info"
    )
