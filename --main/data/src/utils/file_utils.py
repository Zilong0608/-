# -*- coding: utf-8 -*-
"""
文件扫描和工具模块
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Generator
from datetime import datetime
import json
import hashlib

from .logger import get_logger


@dataclass
class FileInfo:
    """文件信息"""
    path: Path
    name: str
    suffix: str
    size: int
    category: str  # 所属岗位/领域
    parent_folder: str  # 直接父文件夹名
    is_template: bool = False  # 是否是简历模板
    needs_ocr: bool = False  # 是否需要OCR
    md5: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'path': str(self.path),
            'name': self.name,
            'suffix': self.suffix,
            'size': self.size,
            'category': self.category,
            'parent_folder': self.parent_folder,
            'is_template': self.is_template,
            'needs_ocr': self.needs_ocr,
            'md5': self.md5,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'FileInfo':
        data['path'] = Path(data['path'])
        return cls(**data)


class FileScanner:
    """文件扫描器"""

    # 简历模板识别关键词
    TEMPLATE_KEYWORDS = [
        '简历', '模板', 'resume', 'template', 'CV',
        '封面', '求职信', '自荐信'
    ]

    # 需要跳过的文件夹
    SKIP_DIR_NAMES = [
        '.git', '.idea', '__pycache__', '.DS_Store',
        'node_modules', '.venv', 'venv', 'env',
        'data_index', 'data_chunks', 'data_ingest',
        'data_reports', 'data_markdown', 'logs', 'tmp', '.cache'
    ]

    # 需要跳过的文件
    SKIP_FILE_NAMES = [
        'Thumbs.db', '.gitignore'
    ]

    # 需要跳过的路径关键字
    SKIP_PATH_KEYWORDS = [
        'ai_rag_demo', 'demo', 'example'
    ]

    def __init__(
        self,
        root_dir: Path,
        supported_formats: List[str],
        ocr_formats: List[str]
    ):
        """
        初始化文件扫描器

        Args:
            root_dir: 扫描根目录
            supported_formats: 支持的文档格式列表
            ocr_formats: 需要OCR的图片格式列表
        """
        self.root_dir = Path(root_dir)
        self.supported_formats = [fmt.lower() for fmt in supported_formats]
        self.ocr_formats = [fmt.lower() for fmt in ocr_formats]
        self.logger = get_logger("file_scanner")

    def scan(self) -> List[FileInfo]:
        """
        扫描目录下所有文件

        Returns:
            文件信息列表
        """
        files = []
        self.logger.info(f"开始扫描目录: {self.root_dir}")

        for file_path in self._walk_files():
            file_info = self._analyze_file(file_path)
            if file_info:
                files.append(file_info)

        self.logger.info(f"扫描完成，共发现 {len(files)} 个有效文件")
        return files

    def _should_skip_path(self, path: Path) -> bool:
        path_str = str(path).lower()
        for keyword in self.SKIP_PATH_KEYWORDS:
            if keyword in path_str:
                return True
        return False

    def _walk_files(self) -> Generator[Path, None, None]:
        """遍历所有文件"""
        for root, dirs, files in os.walk(self.root_dir):
            # 过滤掉需要跳过的目录
            dirs[:] = [
                d for d in dirs
                if d not in self.SKIP_DIR_NAMES
                and not self._should_skip_path(Path(root) / d)
            ]

            for file in files:
                if file in self.SKIP_FILE_NAMES:
                    continue
                file_path = Path(root) / file
                if self._should_skip_path(file_path):
                    continue
                yield file_path

    def _analyze_file(self, file_path: Path) -> Optional[FileInfo]:
        """分析单个文件"""
        suffix = file_path.suffix.lower()

        # 检查是否是支持的格式
        all_formats = self.supported_formats + self.ocr_formats
        if suffix not in all_formats:
            return None

        # 获取相对路径信息
        try:
            rel_path = file_path.relative_to(self.root_dir)
            parts = rel_path.parts
        except ValueError:
            parts = [file_path.parent.name]

        # 确定分类（第一级文件夹名）
        category = parts[0] if len(parts) > 1 else "未分类"

        # 确定直接父文件夹
        parent_folder = file_path.parent.name

        # 判断是否是简历模板
        is_template = self._is_template(file_path, category)

        # 判断是否需要OCR
        needs_ocr = suffix in self.ocr_formats

        return FileInfo(
            path=file_path,
            name=file_path.name,
            suffix=suffix,
            size=file_path.stat().st_size,
            category=category,
            parent_folder=parent_folder,
            is_template=is_template,
            needs_ocr=needs_ocr,
        )

    def _is_template(self, file_path: Path, category: str) -> bool:
        """判断是否是简历模板"""
        suffix = file_path.suffix.lower()
        full_path_str = str(file_path).lower()

        for keyword in self.TEMPLATE_KEYWORDS:
            if keyword.lower() in full_path_str:
                return True

        # HR/简历目录下的文档大概率为模板
        if 'hr' in category.lower() or '简历' in category:
            if suffix in ['.doc', '.docx', '.pdf', '.rtf', '.wps']:
                return True
        return False

    def get_statistics(self, files: List[FileInfo]) -> Dict:
        """
        获取文件统计信息

        Args:
            files: 文件信息列表

        Returns:
            统计信息字典
        """
        stats = {
            'total_files': len(files),
            'total_size': sum(f.size for f in files),
            'by_format': {},
            'by_category': {},
            'templates_count': 0,
            'ocr_needed_count': 0,
            'interview_files_count': 0,  # 面试题文件数量
        }

        for f in files:
            # 按格式统计
            suffix = f.suffix
            if suffix not in stats['by_format']:
                stats['by_format'][suffix] = {'count': 0, 'size': 0}
            stats['by_format'][suffix]['count'] += 1
            stats['by_format'][suffix]['size'] += f.size

            # 按分类统计
            category = f.category
            if category not in stats['by_category']:
                stats['by_category'][category] = {'count': 0, 'size': 0, 'templates': 0}
            stats['by_category'][category]['count'] += 1
            stats['by_category'][category]['size'] += f.size

            # 统计模板
            if f.is_template:
                stats['templates_count'] += 1
                stats['by_category'][category]['templates'] += 1
            else:
                stats['interview_files_count'] += 1

            # 统计需要OCR的文件
            if f.needs_ocr:
                stats['ocr_needed_count'] += 1

        return stats

    def save_scan_result(
        self,
        files: List[FileInfo],
        output_path: Path,
        include_stats: bool = True
    ):
        """
        保存扫描结果

        Args:
            files: 文件信息列表
            output_path: 输出文件路径
            include_stats: 是否包含统计信息
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        result = {
            'scan_time': datetime.now().isoformat(),
            'root_dir': str(self.root_dir),
            'files': [f.to_dict() for f in files],
        }

        if include_stats:
            result['statistics'] = self.get_statistics(files)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        self.logger.info(f"扫描结果已保存到: {output_path}")

    @staticmethod
    def load_scan_result(path: Path) -> tuple:
        """
        加载扫描结果

        Args:
            path: 扫描结果文件路径

        Returns:
            (文件信息列表, 统计信息)
        """
        with open(path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        files = [FileInfo.from_dict(d) for d in result['files']]
        stats = result.get('statistics', {})

        return files, stats


def calculate_md5(file_path: Path, chunk_size: int = 8192) -> str:
    """
    计算文件MD5

    Args:
        file_path: 文件路径
        chunk_size: 读取块大小

    Returns:
        MD5哈希值
    """
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def ensure_dir(path: Path) -> Path:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_file_encoding(file_path: Path) -> str:
    """
    检测文件编码

    Args:
        file_path: 文件路径

    Returns:
        编码名称
    """
    import chardet

    with open(file_path, 'rb') as f:
        raw = f.read(10000)  # 读取前10KB
        result = chardet.detect(raw)
        return result['encoding'] or 'utf-8'
