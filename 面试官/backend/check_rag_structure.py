#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查 RAG 库数据结构
"""

import chromadb
from chromadb.config import Settings

# 连接到 RAG 库
rag_path = r"C:\Users\15048\Desktop\rag库\数据\data_index"

client = chromadb.PersistentClient(
    path=rag_path,
    settings=Settings(
        anonymized_telemetry=False,
        allow_reset=False
    )
)

# 列出所有集合
collections = client.list_collections()
print(f"集合数量: {len(collections)}")
print()

for collection in collections:
    print(f"集合名称: {collection.name}")
    print(f"文档数量: {collection.count()}")
    print()

    # 获取前3条数据查看结构
    results = collection.get(limit=3, include=['documents', 'metadatas'])

    print("=" * 60)
    print("示例数据：")
    print("=" * 60)

    for i in range(min(3, len(results['ids']))):
        print(f"\n【文档 {i+1}】")
        print(f"ID: {results['ids'][i]}")
        print(f"\nDocument: {results['documents'][i][:200]}...")
        print(f"\nMetadata: {results['metadatas'][i]}")
        print("-" * 60)
