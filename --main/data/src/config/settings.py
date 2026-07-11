# -*- coding: utf-8 -*-
"""
配置管理模块
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json


@dataclass
class PathConfig:
    """路径配置"""
    # 项目根目录（数据文件夹）
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)

    @property
    def data_raw(self) -> Path:
        override = os.getenv("RAG_DATA_RAW")
        if override:
            override_path = Path(override)
            if not override_path.is_absolute():
                override_path = self.root_dir / override_path
            return override_path.resolve()
        return self.root_dir / "data_raw"

    @property
    def data_ingest(self) -> Path:
        return self.root_dir / "data_ingest"

    @property
    def data_chunks(self) -> Path:
        return self.root_dir / "data_chunks"

    @property
    def data_index(self) -> Path:
        return self.root_dir / "data_index"

    @property
    def data_reports(self) -> Path:
        return self.root_dir / "data_reports"

    @property
    def data_markdown(self) -> Path:
        return self.root_dir / "data_markdown"

    @property
    def logs_dir(self) -> Path:
        return self.root_dir / "logs"

    @property
    def configs_dir(self) -> Path:
        return self.root_dir / "configs"

    @property
    def tmp_dir(self) -> Path:
        return self.root_dir / "tmp"

    @property
    def src_dir(self) -> Path:
        return self.root_dir / "src"

    @property
    def scripts_dir(self) -> Path:
        return self.root_dir / "scripts"


@dataclass
class ExtractorConfig:
    """文本提取配置"""
    # 支持的文件格式
    supported_formats: List[str] = field(default_factory=lambda: [
        '.pdf', '.doc', '.docx', '.txt', '.md', '.ppt', '.pptx'
    ])

    # 需要OCR的格式
    ocr_formats: List[str] = field(default_factory=lambda: [
        '.jpg', '.jpeg', '.png', '.bmp', '.tiff'
    ])

    # PDF提取器选择: 'pymupdf' 或 'pdfplumber'
    pdf_extractor: str = 'pymupdf'

    # OCR引擎选择: 'paddleocr', 'tesseract' 或 'easyocr'
    ocr_engine: str = 'easyocr'

    # OCR语言
    ocr_lang: str = 'ch'

    # 是否启用OCR（默认关闭，避免扫描版丢失结构）
    enable_ocr: bool = False


@dataclass
class ChunkerConfig:
    """分段配置"""
    # Q&A边界识别模式
    qa_patterns: List[str] = field(default_factory=lambda: [
        r'^#{1,3}\s*\d+[\.、,，]\s*',      # Markdown标题: ## 1. 或 ### 1、
        r'^\d+[\.、,，]\s*',                # 数字编号: 1. 或 1、
        r'^[Qq]\s*[:：]\s*',               # Q: 或 Q：
        r'^问\s*[:：]\s*',                  # 问：
        r'^【.*?】',                        # 【问题】
        r'^\*\*\d+[\.、]',                 # **1. 加粗编号
    ])

    # 答案识别模式
    answer_patterns: List[str] = field(default_factory=lambda: [
        r'^[Aa]\s*[:：]\s*',               # A: 或 A：
        r'^答\s*[:：]\s*',                  # 答：
        r'^【答案】',                       # 【答案】
    ])

    # 最大chunk长度（字符）
    max_chunk_size: int = 1500

    # 最小chunk长度（字符）
    min_chunk_size: int = 50

    # 超长答案切分时的重叠
    overlap_size: int = 100


@dataclass
class MetadataConfig:
    """Metadata配置"""
    # 岗位映射（文件夹名 -> 标准岗位名）
    position_mapping: Dict[str, str] = field(default_factory=lambda: {
        'AI人工智能大模型-简历项目案例': 'AI大模型',
        'AI人工智能大模型-面试八股文&面试题库': 'AI大模型',
        'AI算法工程师面经': 'AI算法',
        'HR面谈求职面试+通用简历模板': 'HR通用',
        'LLM': 'AI大模型',
        'Oracle': '数据库',
        'Python测试开发': '测试开发',
        'SLAM算法': '算法',
        'sql专项练习题': '数据库',
        'web3': 'Web3',
        '八股文': '通用',
        '大数据面试题': '大数据',
        '深度学习面试': '深度学习',
        '数据分析': '数据分析',
        '数据库面试': '数据库',
        '图形算法': '算法',
        '网络安全': '网络安全',
    })

    # 内容分类规则（路径关键词 -> 类别）
    # 面试题：口头问答类
    interview_question_patterns: List[str] = field(default_factory=lambda: [
        '面试八股文', '面试题库', '面经', '面试题', '八股文',
        'LLM', '深度学习面试', '数据库面试', '网络安全',
        'Oracle', 'Python测试开发', 'SLAM算法', 'web3',
        '图形算法', '数据分析', '大数据面试题',
    ])

    # 笔试题：书面测试类
    written_test_patterns: List[str] = field(default_factory=lambda: [
        '笔试', '练习题', '测试题', '行测', 'IQ智力',
        '企业笔试题库', '专项练习',
    ])

    # 面试技巧：经验分享类
    interview_tips_patterns: List[str] = field(default_factory=lambda: [
        '面试技巧', '技巧大全', '面霸', '面试经历', '面试经验',
        '面试成功', '求职', '应聘', '面试准备', '面试攻略',
        '面试必', '薪资', '自我介绍', 'HR面谈',
    ])

    # 简历/其他：非题目类
    other_patterns: List[str] = field(default_factory=lambda: [
        '简历', '模板', 'resume', '项目案例',
    ])

    # 难度关键词
    difficulty_keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        '基础': ['基础', '入门', '简单', '常见', '基本'],
        '进阶': ['进阶', '中级', '深入', '原理'],
        '高级': ['高级', '高阶', '深度', '源码', '底层', '架构'],
    })

    # 问题类型关键词
    question_type_keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        '概念题': ['是什么', '什么是', '定义', '概念', '介绍'],
        '原理题': ['原理', '为什么', '如何工作', '机制', '原因'],
        '对比题': ['区别', '对比', '不同', '优缺点', '比较'],
        '实战题': ['如何实现', '怎么做', '实战', '项目', '经验'],
        '代码题': ['代码', '实现', '写一个', '编程', '算法题'],
        '场景题': ['场景', '案例', '举例', '如果', '遇到'],
    })


@dataclass
class QualityConfig:
    """质量校验配置"""
    # 乱码检测阈值（非中文英文字符占比）
    garbled_threshold: float = 0.3

    # 最小有效内容长度
    min_content_length: int = 20

    # 相似度去重阈值
    dedup_threshold: float = 0.95

    # 抽检比例
    sample_ratio: float = 0.1


@dataclass
class IndexConfig:
    """向量索引配置"""
    # Embedding模型
    embedding_model: str = 'BAAI/bge-large-zh-v1.5'

    # 向量维度
    embedding_dim: int = 1024

    # 向量库类型: 'chroma' 或 'faiss'
    vector_store: str = 'faiss'

    # 检索返回数量
    top_k: int = 5


@dataclass
class Config:
    """主配置类"""
    paths: PathConfig = field(default_factory=PathConfig)
    extractor: ExtractorConfig = field(default_factory=ExtractorConfig)
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    metadata: MetadataConfig = field(default_factory=MetadataConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    index: IndexConfig = field(default_factory=IndexConfig)

    def save(self, path: Optional[Path] = None):
        """保存配置到JSON文件"""
        if path is None:
            path = self.paths.configs_dir / "config.json"

        path.parent.mkdir(parents=True, exist_ok=True)

        # 转换为可序列化的字典
        config_dict = {
            'extractor': {
                'supported_formats': self.extractor.supported_formats,
                'ocr_formats': self.extractor.ocr_formats,
                'pdf_extractor': self.extractor.pdf_extractor,
                'ocr_engine': self.extractor.ocr_engine,
                'ocr_lang': self.extractor.ocr_lang,
                'enable_ocr': self.extractor.enable_ocr,
            },
            'chunker': {
                'qa_patterns': self.chunker.qa_patterns,
                'answer_patterns': self.chunker.answer_patterns,
                'max_chunk_size': self.chunker.max_chunk_size,
                'min_chunk_size': self.chunker.min_chunk_size,
                'overlap_size': self.chunker.overlap_size,
            },
            'metadata': {
                'position_mapping': self.metadata.position_mapping,
                'difficulty_keywords': self.metadata.difficulty_keywords,
                'question_type_keywords': self.metadata.question_type_keywords,
            },
            'quality': {
                'garbled_threshold': self.quality.garbled_threshold,
                'min_content_length': self.quality.min_content_length,
                'dedup_threshold': self.quality.dedup_threshold,
                'sample_ratio': self.quality.sample_ratio,
            },
            'index': {
                'embedding_model': self.index.embedding_model,
                'embedding_dim': self.index.embedding_dim,
                'vector_store': self.index.vector_store,
                'top_k': self.index.top_k,
            }
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: Path) -> 'Config':
        """从JSON文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)

        config = cls()

        if 'extractor' in config_dict:
            for k, v in config_dict['extractor'].items():
                setattr(config.extractor, k, v)

        if 'chunker' in config_dict:
            for k, v in config_dict['chunker'].items():
                setattr(config.chunker, k, v)

        if 'metadata' in config_dict:
            for k, v in config_dict['metadata'].items():
                setattr(config.metadata, k, v)

        if 'quality' in config_dict:
            for k, v in config_dict['quality'].items():
                setattr(config.quality, k, v)

        if 'index' in config_dict:
            for k, v in config_dict['index'].items():
                setattr(config.index, k, v)

        return config


# 全局配置实例
_config: Optional[Config] = None


def get_config() -> Config:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = Config()
    return _config
