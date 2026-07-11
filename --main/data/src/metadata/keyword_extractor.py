# -*- coding: utf-8 -*-
"""
关键词提取器
从文本中提取技术关键词，用于检索增强
"""

import re
from typing import List, Set, Dict, Optional
from collections import Counter
from ..utils.logger import get_logger
from ..parsers.chunker import Chunk


class KeywordExtractor:
    """关键词提取器"""

    # 技术领域关键词库
    TECH_KEYWORDS = {
        # AI/ML
        'transformer', 'attention', 'bert', 'gpt', 'llm', 'embedding',
        'fine-tuning', '微调', 'lora', 'qlora', 'prompt', '预训练',
        'tokenizer', 'decoder', 'encoder', 'self-attention', 'cross-attention',
        '损失函数', 'softmax', 'relu', 'gelu', 'layer normalization',
        'batch normalization', 'dropout', 'adam', 'sgd', '梯度下降',
        '反向传播', 'forward', 'backward', 'inference', '推理',

        # 深度学习
        'cnn', 'rnn', 'lstm', 'gru', '卷积', '池化', '全连接',
        '残差网络', 'resnet', 'vgg', 'inception', 'mobilenet',
        '目标检测', 'yolo', '图像分类', '语义分割', 'gan', 'vae',

        # NLP
        'nlp', '自然语言处理', '分词', '词向量', 'word2vec',
        '命名实体识别', 'ner', '情感分析', '文本分类', '机器翻译',
        'seq2seq', 'beam search', '语言模型', 'perplexity',

        # 网络安全
        'sql注入', 'xss', 'csrf', 'ssrf', '漏洞', '渗透测试',
        'webshell', '木马', '反序列化', '文件上传', '命令注入',
        '越权', '暴力破解', 'ddos', 'waf', '防火墙', '入侵检测',
        '安全审计', '代码审计', '逆向', '加密', 'rsa', 'aes',

        # 数据库
        'mysql', 'postgresql', 'oracle', 'mongodb', 'redis', 'elasticsearch',
        '索引', 'b+树', '事务', 'acid', '隔离级别', '死锁',
        '分库分表', '读写分离', '主从复制', 'sql优化', '执行计划',
        'innodb', 'myisam', '存储引擎', '触发器', '存储过程',

        # 分布式/大数据
        '分布式', 'hadoop', 'spark', 'flink', 'kafka', 'zookeeper',
        'hdfs', 'mapreduce', '数据仓库', 'etl', 'hive', 'presto',
        '流处理', '批处理', '消息队列', 'rabbitmq', '微服务',

        # Python
        'python', 'pandas', 'numpy', 'pytorch', 'tensorflow', 'keras',
        'flask', 'django', 'fastapi', '装饰器', '生成器', '迭代器',
        'asyncio', '协程', '多线程', '多进程', 'gil',

        # 通用
        'api', 'rest', 'graphql', 'http', 'tcp', 'udp', 'websocket',
        '缓存', 'cdn', '负载均衡', '高可用', '容器', 'docker', 'kubernetes',
        'ci/cd', 'git', '单元测试', '集成测试', '性能测试',
    }

    # 停用词
    STOP_WORDS = {
        '的', '了', '是', '在', '和', '有', '个', '就', '不', '也',
        '都', '与', '及', '等', '这', '那', '你', '我', '他', '她',
        '它', '们', '什么', '怎么', '如何', '为什么', '哪些', '可以',
        '一个', '一些', '这个', '那个', '使用', '进行', '通过', '实现',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'can', 'could', 'should', 'may', 'might', 'must', 'shall',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'or', 'and', 'but', 'if', 'then', 'else', 'when', 'where',
        'what', 'which', 'who', 'how', 'why', 'this', 'that', 'these',
    }

    def __init__(self, custom_keywords: Optional[Set[str]] = None):
        """
        初始化关键词提取器

        Args:
            custom_keywords: 自定义关键词集合
        """
        self.logger = get_logger("keyword_extractor")

        # 合并关键词库
        self.keywords = self.TECH_KEYWORDS.copy()
        if custom_keywords:
            self.keywords.update(custom_keywords)

        # 构建关键词匹配模式
        self._build_patterns()

    def _build_patterns(self):
        """构建关键词匹配的正则模式"""
        # 按长度排序，优先匹配长的关键词
        sorted_keywords = sorted(self.keywords, key=len, reverse=True)

        # 转义特殊字符并构建模式
        escaped = [re.escape(kw) for kw in sorted_keywords]
        self.keyword_pattern = re.compile(
            r'\b(' + '|'.join(escaped) + r')\b',
            re.IGNORECASE
        )

    def extract(self, text: str, top_k: int = 10) -> List[str]:
        """
        从文本中提取关键词

        Args:
            text: 输入文本
            top_k: 返回top k个关键词

        Returns:
            关键词列表（按出现频率排序）
        """
        if not text:
            return []

        text_lower = text.lower()

        # 方法1: 匹配预定义关键词
        matches = self.keyword_pattern.findall(text_lower)

        # 方法2: 提取中文技术术语（基于规则）
        chinese_terms = self._extract_chinese_terms(text)

        # 合并结果
        all_keywords = matches + chinese_terms

        # 统计频率并排序
        counter = Counter(all_keywords)
        top_keywords = [kw for kw, _ in counter.most_common(top_k)]

        return top_keywords

    def _extract_chinese_terms(self, text: str) -> List[str]:
        """提取中文技术术语"""
        terms = []

        # 匹配中文技术术语模式
        patterns = [
            r'[\u4e00-\u9fff]{2,6}(?:算法|模型|网络|机制|结构|层|函数|方法|技术|系统|框架|引擎|工具)',
            r'(?:深度|机器|强化|监督|无监督|自监督)学习',
            r'[\u4e00-\u9fff]{2,4}(?:检测|识别|分类|分割|生成|优化|训练|推理|部署)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            terms.extend(matches)

        # 过滤停用词
        terms = [t for t in terms if t not in self.STOP_WORDS and len(t) > 1]

        return terms

    def extract_from_chunk(self, chunk: Chunk) -> List[str]:
        """
        从chunk中提取关键词

        Args:
            chunk: 输入chunk

        Returns:
            关键词列表
        """
        # 优先从问题中提取
        keywords = []

        if chunk.question:
            keywords.extend(self.extract(chunk.question, top_k=5))

        # 从答案中补充
        if chunk.answer:
            answer_keywords = self.extract(chunk.answer, top_k=10)
            for kw in answer_keywords:
                if kw not in keywords:
                    keywords.append(kw)

        return keywords[:10]  # 最多返回10个

    def label_chunks_with_keywords(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        为chunks添加关键词标签

        Args:
            chunks: chunk列表

        Returns:
            添加关键词后的chunk列表
        """
        for chunk in chunks:
            keywords = self.extract_from_chunk(chunk)
            chunk.metadata['keywords'] = keywords

        return chunks

    def add_custom_keywords(self, keywords: Set[str]):
        """
        添加自定义关键词

        Args:
            keywords: 关键词集合
        """
        self.keywords.update(keywords)
        self._build_patterns()
        self.logger.info(f"添加了 {len(keywords)} 个自定义关键词")
