"""
LangChain Embeddings 适配器 — 将 BGE-M3 的 Dense + Sparse 双输出封装为标准接口。

提供:
    - embed_documents / embed_query: 标准 LangChain Embeddings 接口（dense）
    - embed_documents_hybrid / embed_query_hybrid: 扩展接口（dense + sparse）
    - embed_query_hybrid_raw: 原始 numpy 格式，供 VectorStore.search() 使用

用法:
    from rag.lc_embeddings import BGEHybridEmbeddings
    from rag.embedder import Embedder
    from rag.config import EmbedderConfig

    embedder = Embedder(EmbedderConfig())
    lc_emb = BGEHybridEmbeddings(embedder)
    dense_vecs = lc_emb.embed_documents(["文本1", "文本2"])
    hybrid = lc_emb.embed_query_hybrid("查询")
"""

from typing import Dict, List

import numpy as np
from langchain_core.embeddings import Embeddings as LCEmbeddings


class BGEHybridEmbeddings(LCEmbeddings):
    """LangChain 兼容的 BGE-M3 向量化器，支持 Hybrid (Dense + Sparse)。

    标准接口（满足 LangChain Embeddings 协议）：
        - embed_documents(texts) → List[List[float]]
        - embed_query(text) → List[float]

    扩展接口（支持混合检索）：
        - embed_documents_hybrid(texts) → {"dense": np.ndarray, "sparse": List[Dict[int, float]]}
        - embed_query_hybrid(text) → {"dense": np.ndarray, "sparse": List[Dict[int, float]]}
        - embed_query_hybrid_raw(text) → (np.ndarray, Dict[int, float])  # dense_vec, sparse_vec
    """

    def __init__(self, embedder):
        """
        参数:
            embedder: rag.embedder.Embedder 实例（单例）
        """
        self._embedder = embedder

    # ── 标准 LangChain Embeddings 接口 ─────────────────────

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量编码文档（仅返回 dense 向量）。

        参数:
            texts: 文本列表

        返回: dense 向量列表，每个是 dim 维 float 列表
        """
        if not texts:
            return []
        dense = self._embedder.encode_dense(texts)
        return dense.tolist()

    def embed_query(self, text: str) -> List[float]:
        """编码单个查询（仅返回 dense 向量）。

        参数:
            text: 查询文本

        返回: dense 向量（dim 维 float 列表）
        """
        return self.embed_documents([text])[0]

    # ── 扩展接口（Hybrid Dense + Sparse） ─────────────────

    def embed_documents_hybrid(self, texts: List[str]) -> Dict[str, object]:
        """批量编码文档（返回 dense + sparse）。

        参数:
            texts: 文本列表

        返回: {
            "dense": np.ndarray (n, dim),
            "sparse": List[Dict[int, float]]  # [{token_id: weight}, ...]
        }
        """
        if not texts:
            return {"dense": np.zeros((0, self._embedder.dim)), "sparse": []}
        return self._embedder.encode(texts)

    def embed_query_hybrid(self, text: str) -> Dict[str, object]:
        """编码单个查询（返回 dense + sparse）。

        参数:
            text: 查询文本

        返回: {
            "dense": 单条查询的 dense 向量,
            "sparse": 单条查询的 sparse 向量
        }
        """
        result = self._embedder.encode([text])
        return {
            "dense": result["dense"],
            "sparse": result["sparse"],
        }

    def embed_query_hybrid_raw(self, text: str):
        """编码单个查询，直接返回 (dense_vec, sparse_vec) 用于 VectorStore.search()。

        参数:
            text: 查询文本

        返回: (dense_vec: np.ndarray, sparse_vec: Dict[int, float])
        """
        result = self._embedder.encode([text])
        return result["dense"][0], result["sparse"][0]

    # ── 属性 ──────────────────────────────────────────────

    @property
    def dim(self) -> int:
        """Dense 向量维度。"""
        return self._embedder.dim

    @property
    def embedder(self):
        """底层 Embedder 实例。"""
        return self._embedder
