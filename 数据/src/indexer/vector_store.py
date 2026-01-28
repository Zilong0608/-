# -*- coding: utf-8 -*-
"""
向量存储模块
支持 Chroma 和 FAISS
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
import json

from ..utils.logger import get_logger
from ..config.settings import IndexConfig
from ..parsers.chunker import Chunk


@dataclass
class SearchResult:
    """检索结果"""
    chunk_id: str
    content: str
    score: float
    question: Optional[str] = None
    answer: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'chunk_id': self.chunk_id,
            'content': self.content,
            'score': self.score,
            'question': self.question,
            'answer': self.answer,
            'metadata': self.metadata,
        }


class VectorStore:
    """向量存储"""

    def __init__(
        self,
        config: Optional[IndexConfig] = None,
        persist_dir: Optional[Path] = None
    ):
        """
        初始化向量存储

        Args:
            config: 索引配置
            persist_dir: 持久化目录
        """
        self.config = config or IndexConfig()
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.logger = get_logger("vector_store")

        self._store = None
        self._embedder = None
        self._embedding_dim = None

    def _get_embedder(self):
        """延迟加载Embedding模型"""
        if self._embedder is None:
            self.logger.info(f"加载Embedding模型: {self.config.embedding_model}")

            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self.config.embedding_model)
                self.logger.info("Embedding模型加载成功")
            except Exception as e:
                self.logger.error(f"加载Embedding模型失败: {e}")
                raise

        return self._embedder

    def _get_embedding_dim(self) -> int:
        if self._embedding_dim is None:
            embedder = self._get_embedder()
            try:
                self._embedding_dim = int(embedder.get_sentence_embedding_dimension())
            except Exception:
                sample = embedder.encode(["dimension_probe"])
                self._embedding_dim = int(sample.shape[1])
        return self._embedding_dim

    def _init_chroma(self):
        """初始化Chroma向量库"""
        import chromadb
        from chromadb.config import Settings

        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )
        else:
            client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False)
            )

        # 获取或创建collection
        self._store = client.get_or_create_collection(
            name="interview_qa",
            metadata={"hnsw:space": "cosine"}
        )

        # 注意：由于HNSW索引问题，暂时不调用count()
        self.logger.info(f"Chroma向量库初始化完成")

    def _init_faiss(self):
        """初始化FAISS向量库"""
        import faiss
        import numpy as np

        # 创建索引
        dim = self._get_embedding_dim()
        self._faiss_index = faiss.IndexFlatIP(dim)  # 内积相似度

        # 存储chunk信息
        self._faiss_chunks: List[Chunk] = []
        self._faiss_ids: List[str] = []

        # 尝试加载已有索引
        if self.persist_dir:
            index_path = self.persist_dir / "faiss.index"
            chunks_path = self.persist_dir / "faiss_chunks.json"

            if index_path.exists() and chunks_path.exists():
                self._faiss_index = faiss.read_index(str(index_path))
                if self._faiss_index.d != dim:
                    raise ValueError(
                        f"FAISS维度不一致: 索引维度={self._faiss_index.d}, 模型维度={dim}"
                    )
                with open(chunks_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._faiss_chunks = [Chunk.from_dict(d) for d in data['chunks']]
                    self._faiss_ids = data['ids']

                self.logger.info(f"FAISS索引加载完成，当前文档数: {len(self._faiss_ids)}")

        self._store = 'faiss'  # 标记类型

    def initialize(self):
        """初始化向量库"""
        if self.config.vector_store == 'chroma':
            self._init_chroma()
        elif self.config.vector_store == 'faiss':
            self._init_faiss()
        else:
            raise ValueError(f"不支持的向量库类型: {self.config.vector_store}")

    def add_chunks(
        self,
        chunks: List[Chunk],
        batch_size: int = 100,
        show_progress: bool = True
    ):
        """
        添加chunks到向量库

        Args:
            chunks: chunk列表
            batch_size: 批次大小
            show_progress: 是否显示进度
        """
        if self._store is None:
            self.initialize()

        embedder = self._get_embedder()
        total = len(chunks)

        self.logger.info(f"开始添加 {total} 个chunks到向量库...")

        for i in range(0, total, batch_size):
            batch = chunks[i:i+batch_size]

            # 计算embeddings
            texts = [c.content for c in batch]
            embeddings = embedder.encode(texts, normalize_embeddings=True)

            if self.config.vector_store == 'chroma':
                self._add_to_chroma(batch, embeddings.tolist())
            else:
                self._add_to_faiss(batch, embeddings)

            if show_progress:
                progress = min(i + batch_size, total)
                self.logger.info(f"进度: {progress}/{total} ({progress/total*100:.1f}%)")

        self.logger.info(f"添加完成，当前索引大小: {self.count()}")

    def _add_to_chroma(self, chunks: List[Chunk], embeddings: List[List[float]]):
        """添加到Chroma"""
        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = []

        for c in chunks:
            meta = {
                'question': c.question or '',
                'answer': c.answer or '',
                'chunk_type': c.chunk_type,
                'source_file': c.source_file or '',
                'question_num': c.question_num or 0,
            }
            # 添加自定义metadata
            for k, v in c.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                elif isinstance(v, list):
                    meta[k] = json.dumps(v, ensure_ascii=False)
            metadatas.append(meta)

        self._store.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    def _add_to_faiss(self, chunks: List[Chunk], embeddings):
        """添加到FAISS"""
        import numpy as np

        # 添加到索引
        self._faiss_index.add(embeddings.astype(np.float32))

        # 存储chunk信息
        self._faiss_chunks.extend(chunks)
        self._faiss_ids.extend([c.chunk_id for c in chunks])

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict] = None
    ) -> List[SearchResult]:
        """
        检索相关内容

        Args:
            query: 查询文本
            top_k: 返回数量
            filter_metadata: metadata过滤条件

        Returns:
            检索结果列表
        """
        if self._store is None:
            self.initialize()

        k = top_k or self.config.top_k
        embedder = self._get_embedder()

        # 计算query的embedding
        query_embedding = embedder.encode([query], normalize_embeddings=True)

        if self.config.vector_store == 'chroma':
            return self._search_chroma(query_embedding[0].tolist(), k, filter_metadata)
        else:
            return self._search_faiss(query_embedding, k, filter_metadata)

    def _search_chroma(
        self,
        query_embedding: List[float],
        top_k: int,
        filter_metadata: Optional[Dict]
    ) -> List[SearchResult]:
        """从Chroma检索"""
        where = None
        if filter_metadata:
            where = filter_metadata

        results = self._store.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=['documents', 'metadatas', 'distances']
        )

        search_results = []
        if results['ids'] and results['ids'][0]:
            for i, chunk_id in enumerate(results['ids'][0]):
                # Chroma返回的是距离，转换为相似度分数
                distance = results['distances'][0][i] if results['distances'] else 0
                score = 1 - distance  # 余弦距离转相似度

                meta = results['metadatas'][0][i] if results['metadatas'] else {}

                search_results.append(SearchResult(
                    chunk_id=chunk_id,
                    content=results['documents'][0][i],
                    score=score,
                    question=meta.get('question'),
                    answer=meta.get('answer'),
                    metadata=meta,
                ))

        return search_results

    def _search_faiss(
        self,
        query_embedding,
        top_k: int,
        filter_metadata: Optional[Dict]
    ) -> List[SearchResult]:
        """从FAISS检索"""
        import numpy as np

        # 检索
        scores, indices = self._faiss_index.search(
            query_embedding.astype(np.float32),
            top_k * 2 if filter_metadata else top_k  # 如果有过滤，多检索一些
        )

        search_results = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self._faiss_chunks):
                continue

            chunk = self._faiss_chunks[idx]

            # 应用过滤
            if filter_metadata:
                match = True
                for key, value in filter_metadata.items():
                    chunk_value = chunk.metadata.get(key)
                    if chunk_value != value:
                        match = False
                        break
                if not match:
                    continue

            search_results.append(SearchResult(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                score=float(scores[0][i]),
                question=chunk.question,
                answer=chunk.answer,
                metadata=chunk.metadata,
            ))

            if len(search_results) >= top_k:
                break

        return search_results

    def count(self) -> int:
        """获取索引中的文档数量"""
        if self._store is None:
            return 0

        if self.config.vector_store == 'chroma':
            return self._store.count()
        else:
            return len(self._faiss_ids)

    def save(self):
        """保存索引"""
        if self.persist_dir is None:
            self.logger.warning("未设置持久化目录，跳过保存")
            return

        self.persist_dir.mkdir(parents=True, exist_ok=True)

        if self.config.vector_store == 'chroma':
            # Chroma自动持久化
            self.logger.info(f"Chroma索引已自动保存到: {self.persist_dir}")
        else:
            # 保存FAISS索引
            import faiss

            index_path = self.persist_dir / "faiss.index"
            chunks_path = self.persist_dir / "faiss_chunks.json"

            faiss.write_index(self._faiss_index, str(index_path))

            with open(chunks_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'ids': self._faiss_ids,
                    'chunks': [c.to_dict() for c in self._faiss_chunks]
                }, f, ensure_ascii=False)

            meta_path = self.persist_dir / "faiss_meta.json"
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'embedding_model': self.config.embedding_model,
                    'embedding_dim': self._get_embedding_dim(),
                }, f, ensure_ascii=False, indent=2)

            self.logger.info(f"FAISS索引已保存到: {self.persist_dir}")

    def clear(self):
        """清空索引"""
        if self.config.vector_store == 'chroma' and self._store:
            # 删除并重建collection
            import chromadb
            client = self._store._client
            client.delete_collection("interview_qa")
            self._store = client.create_collection(
                name="interview_qa",
                metadata={"hnsw:space": "cosine"}
            )
        elif self.config.vector_store == 'faiss':
            import faiss
            dim = self._get_embedding_dim()
            self._faiss_index = faiss.IndexFlatIP(dim)
            self._faiss_chunks = []
            self._faiss_ids = []

        self.logger.info("索引已清空")

    def get_chunk_by_id(self, chunk_id: str) -> Optional[Chunk]:
        """
        根据ID获取chunk

        Args:
            chunk_id: chunk ID

        Returns:
            Chunk对象或None
        """
        if self.config.vector_store == 'chroma' and self._store:
            result = self._store.get(ids=[chunk_id], include=['documents', 'metadatas'])
            if result['ids']:
                meta = result['metadatas'][0] if result['metadatas'] else {}
                return Chunk(
                    chunk_id=chunk_id,
                    content=result['documents'][0],
                    question=meta.get('question'),
                    answer=meta.get('answer'),
                    chunk_type=meta.get('chunk_type', 'text'),
                    source_file=meta.get('source_file'),
                    question_num=meta.get('question_num'),
                    metadata=meta,
                )
        elif self.config.vector_store == 'faiss':
            for chunk in self._faiss_chunks:
                if chunk.chunk_id == chunk_id:
                    return chunk

        return None
