"""
向量库模块 — ChromaDB 存储与检索。

职责单一：向量的 CRUD 和相似度检索。
异常隔离：ChromaDB 操作失败不影响上层逻辑。
"""

from typing import Any, Dict, List, Optional

import numpy as np

from rag.config import StoreConfig, SearchConfig


def _safe_zscore(x: np.ndarray) -> np.ndarray:
    """Z-score 归一化，处理常数数组。"""
    std = np.std(x)
    if std < 1e-8:
        return np.zeros_like(x)
    return (x - np.mean(x)) / std


class _NoOpEmbeddingFunction:
    """禁用 ChromaDB 自带 embedding — 使用外部 bge-m3。"""
    def __call__(self, input):
        raise RuntimeError("ChromaDB built-in embedding disabled")

    def name(self):
        return "noop"


class VectorStore:
    """ChromaDB 向量库，存储 dense + sparse + metadata。"""

    def __init__(self, config: StoreConfig = None):
        self._config = config or StoreConfig()
        self._client = None
        self._collection = None
        self._doc_sparse: Dict[str, Dict[int, float]] = {}
        self._doc_text: Dict[str, str] = {}

    # ── 惰性初始化 ────────────────────────────────────────

    def _ensure_client(self):
        if self._client is not None:
            return
        # Windows DLL 加载顺序: sentence_transformers 必须在 chromadb 之前导入
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
        except ImportError:
            pass
        import chromadb
        self._client = chromadb.PersistentClient(path=self._config.persist_dir)

    def _ensure_collection(self):
        if self._collection is not None:
            return
        self._ensure_client()
        name = self._config.collection_name
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": self._config.hnsw_space},
            embedding_function=_NoOpEmbeddingFunction(),
        )

    # ── 写入 ──────────────────────────────────────────────

    def add(
        self,
        texts: List[str],
        dense_vecs: np.ndarray,
        sparse_vecs: List[Dict[int, float]],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """批量写入 chunks。返回 id 列表。"""
        self._ensure_collection()

        n = len(texts)
        if ids is None:
            base = self._collection.count()
            ids = [f"chunk_{base + i}" for i in range(n)]

        self._collection.add(
            ids=ids,
            embeddings=dense_vecs.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

        # 本地缓存 sparse + 文本
        for i, cid in enumerate(ids):
            self._doc_sparse[cid] = sparse_vecs[i]
            self._doc_text[cid] = texts[i]

        return ids

    def delete(self, ids: List[str]) -> None:
        """删除指定 chunk。"""
        if self._collection:
            self._collection.delete(ids=ids)
        for cid in ids:
            self._doc_sparse.pop(cid, None)
            self._doc_text.pop(cid, None)

    # ── 检索 ──────────────────────────────────────────────

    def search(
        self,
        query_dense: np.ndarray,
        query_sparse: Dict[int, float],
        search_config: SearchConfig = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索: dense(ChromaDB ANN) + sparse(local re-score)。

        参数:
            query_dense: 查询的 dense 向量 (dim,)
            query_sparse: 查询的 sparse 向量 {token_id: weight}
            search_config: 检索配置

        返回: [{id, content, score, metadata, dense_score, sparse_score}]
        """
        self._ensure_collection()
        cfg = search_config or SearchConfig()

        if self._collection.count() == 0:
            return []

        # Dense 检索: 取 top_k * multiplier 候选
        n_candidates = min(
            cfg.top_k * cfg.candidate_multiplier,
            self._collection.count(),
        )
        dense_results = self._collection.query(
            query_embeddings=[query_dense.tolist()],
            n_results=n_candidates,
            include=["documents", "metadatas", "distances"],
        )

        # Sparse 重打分
        ids_candidate = dense_results["ids"][0]
        distances = dense_results["distances"][0]

        # cosine distance → cosine similarity
        d_scores = np.array([1.0 - d / 2.0 for d in distances])

        s_scores = np.zeros(len(ids_candidate))
        for i, cid in enumerate(ids_candidate):
            sparse = self._doc_sparse.get(cid, {})
            s_scores[i] = sum(
                query_sparse.get(tid, 0.0) * sparse.get(tid, 0.0)
                for tid in query_sparse
            )

        # Z-score 归一化 + 加权融合
        d_norm = _safe_zscore(d_scores)
        s_norm = _safe_zscore(s_scores)
        hybrid = cfg.alpha * d_norm + (1 - cfg.alpha) * s_norm

        # 排序取 top_k
        top_idx = np.argsort(-hybrid)[:cfg.top_k]

        results = []
        for i in top_idx:
            cid = ids_candidate[i]
            results.append({
                "id": cid,
                "content": (
                    dense_results["documents"][0][i]
                    if dense_results["documents"]
                    else self._doc_text.get(cid, "")
                ),
                "score": round(float(hybrid[i]), 4),
                "dense_score": round(float(d_scores[i]), 4),
                "sparse_score": round(float(s_scores[i]), 4),
                "metadata": (
                    dense_results["metadatas"][0][i]
                    if dense_results["metadatas"]
                    else {}
                ),
            })

        return results

    # ── 管理 ──────────────────────────────────────────────

    @property
    def count(self) -> int:
        self._ensure_collection()
        return self._collection.count()

    def list_collections(self) -> List[str]:
        self._ensure_client()
        return [c.name for c in self._client.list_collections()]

    def drop_collection(self, name: str = None) -> None:
        """删除 collection。"""
        self._ensure_client()
        name = name or self._config.collection_name
        try:
            self._client.delete_collection(name)
        except Exception:
            pass
        self._collection = None
        self._doc_sparse.clear()
        self._doc_text.clear()
