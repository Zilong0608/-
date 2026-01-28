# -*- coding: utf-8 -*-
"""
问题仓库服务 - 连接 RAG 向量数据库
"""

import json
import random
import sys
from typing import List, Optional, Dict, Any
from pathlib import Path

# 添加数据目录到Python路径，以便导入VectorStore
rag_data_path = Path(__file__).parent.parent.parent.parent.parent / "数据"
if rag_data_path.exists():
    sys.path.insert(0, str(rag_data_path))

from ..models import Question, QuestionType, DifficultyLevel
from ..utils.logger import get_logger
from ..utils.exceptions import RAGConnectionException, QuestionPoolEmptyException

logger = get_logger("question_service")


class JsonQuestionRepository:
    """
    JSON-based question repository (no vector store).
    """

    def __init__(
        self,
        json_path: str,
        preload_count: int = 100,
        refill_threshold: int = 20
    ):
        self.json_path = Path(json_path)
        self.preload_count = preload_count
        self.refill_threshold = refill_threshold

        self.question_pool: List[Question] = []
        self._all_questions: List[Question] = []
        self._all_questions_by_category: Dict[str, List[Question]] = {}
        self._current_category: Optional[str] = None
        self._category_display_map = {
            "LLM": "LLM大模型",
            "Oracle": "Oracle数据库",
            "SLAM": "SLAM定位/视觉",
            "Web3": "Web3区块链",
            "数据库": "数据库基础",
            "测试": "测试开发",
            "算法": "算法与图形",
            "网安": "网络安全",
            "其他": "综合题目"
        }

        self._load_questions()

    def _load_questions(self):
        if not self.json_path.exists():
            raise RAGConnectionException(f"Question JSON not found at: {self.json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._all_questions = self._parse_questions(data)
        if not self._all_questions:
            raise QuestionPoolEmptyException("No questions found in JSON file")

    def _parse_questions(self, data: Any) -> List[Question]:
        questions: List[Question] = []

        categories = data.get("categories") if isinstance(data, dict) else None
        if isinstance(categories, dict):
            for category_key, payload in categories.items():
                items = payload.get("questions", []) if isinstance(payload, dict) else []
                parsed = self._parse_question_items(items, category_key)
                if parsed:
                    self._all_questions_by_category[category_key] = parsed
                    questions.extend(parsed)
        else:
            items = data.get("questions") or data.get("items") if isinstance(data, dict) else data
            parsed = self._parse_question_items(items or [], None)
            questions.extend(parsed)

        # 全量去重（避免混合题库时重复）
        seen = set()
        unique_questions = []
        for q in questions:
            if q.content in seen:
                continue
            seen.add(q.content)
            unique_questions.append(q)

        return unique_questions

    def _parse_question_items(self, items: List[Any], category_key: Optional[str]) -> List[Question]:
        questions: List[Question] = []
        seen = set()
        display_category = self._get_display_category(category_key)

        for idx, item in enumerate(items, start=1):
            question_text = ""
            answer_text = ""
            source_file = ""
            metadata = {}
            qid = ""

            if isinstance(item, str):
                question_text = item.strip()
                qid = f"json_{category_key or 'all'}_{idx:06d}"
            elif isinstance(item, dict):
                question_text = (item.get("question") or item.get("content") or "").strip()
                answer_text = (item.get("answer") or "").strip()
                qid = item.get("chunk_id") or item.get("question_id") or f"json_{category_key or 'all'}_{idx:06d}"
                source_file = item.get("source_file") or item.get("metadata", {}).get("source_file", "")
                metadata = item.get("metadata") or {}

            if not question_text:
                continue
            if question_text in seen:
                continue
            seen.add(question_text)

            if category_key:
                metadata = {**metadata, "category_key": category_key, "category_name": display_category}

            job_category = display_category or self._infer_job_category(source_file)

            questions.append(Question(
                question_id=str(qid),
                content=question_text,
                reference_answer=answer_text,
                question_type=QuestionType.CONCEPT,
                difficulty=DifficultyLevel.INTERMEDIATE,
                keywords=[],
                job_category=job_category,
                metadata=metadata
            ))

        return questions

    def list_categories(self) -> List[Dict[str, Any]]:
        categories = []
        for key, items in sorted(self._all_questions_by_category.items()):
            categories.append({
                "key": key,
                "name": self._get_display_category(key) or key,
                "count": len(items)
            })
        return categories

    def _get_display_category(self, key: Optional[str]) -> str:
        if not key:
            return ""
        return self._category_display_map.get(key, key)

    def preload_questions(
        self,
        job_type: Optional[str] = None,
        difficulty: Optional[DifficultyLevel] = None,
        question_type: Optional[QuestionType] = None,
        question_category: Optional[str] = None
    ) -> List[Question]:
        if not self._all_questions:
            raise QuestionPoolEmptyException("No questions loaded from JSON")

        self._current_category = question_category
        if question_category:
            questions = list(self._all_questions_by_category.get(question_category, []))
        else:
            questions = list(self._all_questions)
        random.shuffle(questions)
        self.question_pool = questions[:self.preload_count]
        return self.question_pool

    def get_next_question(
        self,
        exclude_ids: Optional[List[str]] = None,
        job_type: Optional[str] = None,
        difficulty: Optional[DifficultyLevel] = None,
        question_category: Optional[str] = None
    ) -> Optional[Question]:
        exclude_ids = exclude_ids or []
        available = [q for q in self.question_pool if q.question_id not in exclude_ids]

        if len(available) < self.refill_threshold:
            self._refill_question_pool(exclude_ids)
            available = [q for q in self.question_pool if q.question_id not in exclude_ids]

        if not available:
            return None

        return random.choice(available)

    def _refill_question_pool(self, exclude_ids: List[str]):
        source = self._all_questions
        if self._current_category:
            source = self._all_questions_by_category.get(self._current_category, [])
        questions = [q for q in source if q.question_id not in exclude_ids]
        random.shuffle(questions)
        self.question_pool.extend(questions[: self.preload_count])

        seen = set()
        unique_pool = []
        for q in self.question_pool:
            if q.question_id in seen:
                continue
            seen.add(q.question_id)
            unique_pool.append(q)
        self.question_pool = unique_pool

    def search_questions_by_keyword(self, keyword: str, top_k: int = 10) -> List[Question]:
        if not keyword:
            return []
        matches = [q for q in self._all_questions if keyword in q.content]
        return matches[:top_k]

    def test_connection(self) -> bool:
        try:
            return bool(self._all_questions)
        except Exception:
            return False

    def _infer_job_category(self, source_file: str) -> str:
        source_file = (source_file or "").lower()

        if 'java' in source_file or 'spring' in source_file:
            return 'Java开发'
        elif 'python' in source_file or 'django' in source_file or 'flask' in source_file:
            return 'Python开发'
        elif 'javascript' in source_file or 'js' in source_file or 'react' in source_file or 'vue' in source_file:
            return '前端开发'
        elif 'c++' in source_file or 'cpp' in source_file:
            return 'C++开发'
        elif 'go' in source_file or 'golang' in source_file:
            return 'Go开发'
        elif 'database' in source_file or 'mysql' in source_file or 'sql' in source_file:
            return '数据库'
        elif 'algorithm' in source_file or '算法' in source_file:
            return '算法'
        elif 'system' in source_file or '系统' in source_file:
            return '系统设计'
        elif 'hr' in source_file or '面试' in source_file or '面谈' in source_file:
            return 'HR面试'
        else:
            return '通用'


class QuestionRepository:
    """
    问题仓库 - 管理问题的检索和预加载

    使用用户已有的RAG数据库的VectorStore类
    """

    def __init__(
        self,
        vector_store_path: str,
        preload_count: int = 100,
        refill_threshold: int = 20
    ):
        """
        初始化

        Args:
            vector_store_path: ChromaDB 存储路径
            preload_count: 预加载问题数量
            refill_threshold: 触发补充的阈值
        """
        self.vector_store_path = Path(vector_store_path)
        self.preload_count = preload_count
        self.refill_threshold = refill_threshold

        self.vector_store = None
        self.question_pool: List[Question] = []

        self._connect()

    def _connect(self):
        """连接到 RAG 向量数据库"""
        try:
            if not self.vector_store_path.exists():
                raise RAGConnectionException(
                    f"Vector store not found at: {self.vector_store_path}"
                )

            logger.info(f"Connecting to RAG database at {self.vector_store_path}")

            # 导入用户的VectorStore类
            try:
                from src.indexer.vector_store import VectorStore
                from src.config.settings import IndexConfig
            except ImportError as ie:
                raise RAGConnectionException(
                    f"Failed to import RAG components: {ie}. "
                    "Make sure the data directory is accessible."
                )

            # 创建索引配置（使用ChromaDB）
            config = IndexConfig(
                vector_store='chroma',
                embedding_model='BAAI/bge-large-zh-v1.5',
                embedding_dim=1024,
                top_k=10
            )

            # 初始化VectorStore
            self.vector_store = VectorStore(
                config=config,
                persist_dir=self.vector_store_path
            )
            self.vector_store.initialize()

            logger.info(f"Connected to RAG database successfully")

        except Exception as e:
            logger.error(f"Failed to connect to RAG database: {e}")
            raise RAGConnectionException(str(e))

    def preload_questions(
        self,
        job_type: Optional[str] = None,
        difficulty: Optional[DifficultyLevel] = None,
        question_type: Optional[QuestionType] = None,
        question_category: Optional[str] = None
    ) -> List[Question]:
        """
        预加载问题池

        注意：当前RAG库不支持按job_type/difficulty/question_type过滤，
        这些参数会被忽略，从整个库中随机抽取

        Args:
            job_type: 岗位类型过滤（暂不支持，参数保留用于兼容）
            difficulty: 难度过滤（暂不支持，参数保留用于兼容）
            question_type: 问题类型过滤（暂不支持，参数保留用于兼容）

        Returns:
            预加载的问题列表

        Raises:
            QuestionPoolEmptyException: 没有找到符合条件的问题
        """
        logger.info(f"Preloading {self.preload_count} questions from RAG database")

        try:
            # 使用多个查询词来获取多样化的问题
            query_terms = ["面试问题", "技术问题", "编程问题", "算法", "系统设计"]
            all_questions = []

            for term in query_terms:
                # 使用 VectorStore.search() 进行检索
                results = self.vector_store.search(
                    query=term,
                    top_k=self.preload_count // len(query_terms) + 10
                )

                # 转换 SearchResult 为 Question 对象
                for result in results:
                    try:
                        question_text = result.question or result.content
                        if not question_text or not question_text.strip():
                            continue

                        source_file = result.metadata.get('source_file', '')
                        job_category = self._infer_job_category(source_file)

                        question = Question(
                            question_id=result.chunk_id,
                            content=question_text.strip(),
                            reference_answer=(result.answer or '').strip(),
                            question_type=QuestionType.CONCEPT,
                            difficulty=DifficultyLevel.INTERMEDIATE,
                            keywords=[],
                            job_category=job_category
                        )

                        all_questions.append(question)

                    except Exception as e:
                        logger.warning(f"Failed to parse search result: {e}")
                        continue

            if not all_questions:
                raise QuestionPoolEmptyException("No questions found in RAG database")

            # 去重
            seen_ids = set()
            unique_questions = []
            for q in all_questions:
                if q.question_id not in seen_ids:
                    seen_ids.add(q.question_id)
                    unique_questions.append(q)

            # 随机打乱
            random.shuffle(unique_questions)

            # 取前 preload_count 个
            self.question_pool = unique_questions[:self.preload_count]
            logger.info(f"Preloaded {len(self.question_pool)} questions")

            return self.question_pool

        except Exception as e:
            logger.error(f"Failed to preload questions: {e}")
            raise

    def get_next_question(
        self,
        exclude_ids: Optional[List[str]] = None,
        job_type: Optional[str] = None,
        difficulty: Optional[DifficultyLevel] = None,
        question_category: Optional[str] = None
    ) -> Optional[Question]:
        """
        获取下一个问题

        Args:
            exclude_ids: 排除的问题ID列表（已问过的）
            job_type: 岗位类型
            difficulty: 难度

        Returns:
            下一个问题，如果没有则返回None
        """
        exclude_ids = exclude_ids or []

        # 从问题池中筛选
        available = [
            q for q in self.question_pool
            if q.question_id not in exclude_ids
        ]

        # 如果剩余问题少于阈值，触发补充
        if len(available) < self.refill_threshold:
            logger.info(
                f"Question pool low ({len(available)} remaining), refilling..."
            )
            self._refill_question_pool(exclude_ids, job_type, difficulty)
            available = [
                q for q in self.question_pool
                if q.question_id not in exclude_ids
            ]

        if not available:
            logger.warning("No more questions available in pool")
            return None

        # 随机选择一个
        question = random.choice(available)
        logger.debug(f"Selected question: {question.question_id}")

        return question

    def _refill_question_pool(
        self,
        exclude_ids: List[str],
        job_type: Optional[str] = None,
        difficulty: Optional[DifficultyLevel] = None,
        question_category: Optional[str] = None
    ):
        """
        补充问题池

        Args:
            exclude_ids: 排除的问题ID
            job_type: 岗位类型（暂不支持，参数保留用于兼容）
            difficulty: 难度（暂不支持，参数保留用于兼容）
        """
        try:
            # 使用不同的查询词
            query_terms = ["算法题", "系统设计", "项目经验", "数据结构"]
            all_questions = []

            for term in query_terms:
                results = self.vector_store.search(
                    query=term,
                    top_k=self.preload_count // len(query_terms) + 5
                )

                for result in results:
                    try:
                        question_text = result.question or result.content
                        if not question_text or not question_text.strip():
                            continue

                        source_file = result.metadata.get('source_file', '')
                        job_category = self._infer_job_category(source_file)

                        question = Question(
                            question_id=result.chunk_id,
                            content=question_text.strip(),
                            reference_answer=(result.answer or '').strip(),
                            question_type=QuestionType.CONCEPT,
                            difficulty=DifficultyLevel.INTERMEDIATE,
                            keywords=[],
                            job_category=job_category
                        )

                        all_questions.append(question)

                    except Exception as e:
                        logger.warning(f"Failed to parse search result: {e}")
                        continue

            # 过滤掉已排除的
            new_questions = [
                q for q in all_questions
                if q.question_id not in exclude_ids
            ]

            # 添加到问题池（去重）
            existing_ids = {q.question_id for q in self.question_pool}
            for q in new_questions:
                if q.question_id not in existing_ids:
                    self.question_pool.append(q)

            logger.info(f"Refilled question pool, now has {len(self.question_pool)} questions")

        except Exception as e:
            logger.error(f"Failed to refill question pool: {e}")

    def search_questions_by_keyword(
        self,
        keyword: str,
        top_k: int = 10
    ) -> List[Question]:
        """
        通过关键词搜索问题（RAG检索）

        Args:
            keyword: 搜索关键词
            top_k: 返回Top K结果

        Returns:
            匹配的问题列表
        """
        try:
            logger.debug(f"Searching questions by keyword: {keyword}")

            results = self.vector_store.search(
                query=keyword,
                top_k=top_k
            )

            if not results:
                logger.warning(f"No questions found for keyword: {keyword}")
                return []

            questions = []
            for result in results:
                try:
                    question_text = result.question or result.content
                    if not question_text or not question_text.strip():
                        continue

                    source_file = result.metadata.get('source_file', '')
                    job_category = self._infer_job_category(source_file)

                    question = Question(
                        question_id=result.chunk_id,
                        content=question_text.strip(),
                        reference_answer=(result.answer or '').strip(),
                        question_type=QuestionType.CONCEPT,
                        difficulty=DifficultyLevel.INTERMEDIATE,
                        keywords=[],
                        job_category=job_category
                    )

                    questions.append(question)

                except Exception as e:
                    logger.warning(f"Failed to parse search result: {e}")
                    continue

            logger.debug(f"Found {len(questions)} questions for keyword: {keyword}")

            return questions

        except Exception as e:
            logger.error(f"Failed to search questions: {e}")
            return []

    def _build_filter(
        self,
        job_type: Optional[str] = None,
        difficulty: Optional[DifficultyLevel] = None,
        question_type: Optional[QuestionType] = None
    ) -> Optional[Dict]:
        """
        构建 ChromaDB 查询过滤条件

        Args:
            job_type: 岗位类型
            difficulty: 难度
            question_type: 问题类型

        Returns:
            过滤条件字典
        """
        filters = {}

        if job_type:
            filters["job_category"] = job_type

        if difficulty:
            filters["difficulty"] = difficulty.value

        if question_type:
            filters["question_type"] = question_type.value

        if not filters:
            return None

        # ChromaDB 使用 $and 连接多个条件
        if len(filters) == 1:
            return filters
        else:
            return {"$and": [{k: v} for k, v in filters.items()]}

    def _parse_results(self, results: Dict) -> List[Question]:
        """
        解析 ChromaDB get() 结果为 Question 对象

        RAG库实际metadata结构：
        - question: 问题内容
        - answer: 答案内容
        - source_file: 来源文件
        - chunk_type: 块类型
        - question_num: 问题编号

        Args:
            results: ChromaDB 返回的结果

        Returns:
            Question 对象列表
        """
        questions = []

        ids = results.get('ids', [])
        documents = results.get('documents', [])
        metadatas = results.get('metadatas', [])

        for i, qid in enumerate(ids):
            try:
                metadata = metadatas[i] if i < len(metadatas) else {}
                document = documents[i] if i < len(documents) else ""

                # 优先使用metadata中的question字段，否则使用document
                question_text = metadata.get('question', '').strip()
                if not question_text:
                    question_text = document.strip()

                # 跳过空问题
                if not question_text:
                    continue

                # 从source_file推断job_category（简单处理）
                source_file = metadata.get('source_file', '')
                job_category = self._infer_job_category(source_file)

                question = Question(
                    question_id=qid,
                    content=question_text,
                    reference_answer=metadata.get('answer', '').strip(),
                    question_type=QuestionType.CONCEPT,  # 默认概念题
                    difficulty=DifficultyLevel.INTERMEDIATE,  # 默认中等难度
                    keywords=[],  # RAG库没有关键词字段
                    job_category=job_category
                )

                questions.append(question)

            except Exception as e:
                logger.warning(f"Failed to parse question {qid}: {e}")
                continue

        return questions

    def _parse_query_results(self, results: Dict) -> List[Question]:
        """
        解析 ChromaDB query() 结果为 Question 对象

        Args:
            results: ChromaDB 返回的查询结果

        Returns:
            Question 对象列表
        """
        questions = []

        # query() 返回的结果是嵌套的列表
        # 如果是多个查询，需要遍历所有结果
        all_ids = results.get('ids', [])
        all_documents = results.get('documents', [])
        all_metadatas = results.get('metadatas', [])

        # 遍历每个查询的结果
        for query_idx in range(len(all_ids)):
            ids = all_ids[query_idx] if query_idx < len(all_ids) else []
            documents = all_documents[query_idx] if query_idx < len(all_documents) else []
            metadatas = all_metadatas[query_idx] if query_idx < len(all_metadatas) else []

            for i, qid in enumerate(ids):
                try:
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    document = documents[i] if i < len(documents) else ""

                    # 优先使用metadata中的question字段，否则使用document
                    question_text = metadata.get('question', '').strip()
                    if not question_text:
                        question_text = document.strip()

                    # 跳过空问题
                    if not question_text:
                        continue

                    # 从source_file推断job_category（简单处理）
                    source_file = metadata.get('source_file', '')
                    job_category = self._infer_job_category(source_file)

                    question = Question(
                        question_id=qid,
                        content=question_text,
                        reference_answer=metadata.get('answer', '').strip(),
                        question_type=QuestionType.CONCEPT,  # 默认概念题
                        difficulty=DifficultyLevel.INTERMEDIATE,  # 默认中等难度
                        keywords=[],  # RAG库没有关键词字段
                        job_category=job_category
                    )

                    questions.append(question)

                except Exception as e:
                    logger.warning(f"Failed to parse question {qid}: {e}")
                    continue

        return questions

    def _infer_job_category(self, source_file: str) -> str:
        """
        从来源文件名推断岗位类型

        Args:
            source_file: 来源文件路径

        Returns:
            岗位类型
        """
        source_file = source_file.lower()

        # 简单的关键词匹配
        if 'java' in source_file or 'spring' in source_file:
            return 'Java开发'
        elif 'python' in source_file or 'django' in source_file or 'flask' in source_file:
            return 'Python开发'
        elif 'javascript' in source_file or 'js' in source_file or 'react' in source_file or 'vue' in source_file:
            return '前端开发'
        elif 'c++' in source_file or 'cpp' in source_file:
            return 'C++开发'
        elif 'go' in source_file or 'golang' in source_file:
            return 'Go开发'
        elif 'database' in source_file or 'mysql' in source_file or 'sql' in source_file:
            return '数据库'
        elif 'algorithm' in source_file or '算法' in source_file:
            return '算法'
        elif 'system' in source_file or '系统' in source_file:
            return '系统设计'
        elif 'hr' in source_file or '面试' in source_file or '面谈' in source_file:
            return 'HR面试'
        else:
            return '通用'

    def test_connection(self) -> bool:
        """
        测试 RAG 连接

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # 只检查VectorStore对象是否已初始化，不真正执行搜索
            # 因为搜索可能触发HNSW索引问题
            if self.vector_store and self.vector_store._store:
                logger.info("RAG connection test successful (VectorStore initialized)")
                return True
            return False
        except Exception as e:
            logger.error(f"RAG connection test failed: {e}")
            return False
