"""
向量库模块 — ChromaDB 存储与检索。

职责单一：向量的 CRUD 和相似度检索。
异常隔离：ChromaDB 操作失败不影响上层逻辑。

Sparse 向量通过 SQLite 持久化，重启后自动恢复。
"""

import json
import sqlite3
from pathlib import Path
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
        self._sqlite_conn: Optional[sqlite3.Connection] = None

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

    def _init_sqlite(self):
        """初始化 SQLite 连接并加载 sparse 缓存。"""
        if self._sqlite_conn is not None:
            return
        db_path = Path(self._config.persist_dir) / "sparse_store.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(str(db_path))
        self._sqlite_conn.execute(
            "CREATE TABLE IF NOT EXISTS sparse_vectors "
            "(id TEXT PRIMARY KEY, sparse_json TEXT NOT NULL)"
        )
        self._sqlite_conn.commit()
        cursor = self._sqlite_conn.execute("SELECT id, sparse_json FROM sparse_vectors")
        for row in cursor:
            raw = json.loads(row[1])
            self._doc_sparse[row[0]] = {int(k): v for k, v in raw.items()}

    def _ensure_collection(self):
        if self._collection is not None:
            return
        self._ensure_client()
        self._init_sqlite()
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

        # 持久化 sparse 向量到 SQLite + 内存缓存
        rows = []
        for i, cid in enumerate(ids):
            self._doc_sparse[cid] = sparse_vecs[i]
            rows.append((cid, json.dumps(sparse_vecs[i])))
        self._sqlite_conn.executemany(
            "INSERT OR REPLACE INTO sparse_vectors (id, sparse_json) VALUES (?, ?)",
            rows,
        )
        self._sqlite_conn.commit()

        return ids

    def delete(self, ids: List[str]) -> None:
        """删除指定 chunk。"""
        if self._collection:
            self._collection.delete(ids=ids)
        for cid in ids:
            self._doc_sparse.pop(cid, None)
        if self._sqlite_conn:
            self._sqlite_conn.executemany(
                "DELETE FROM sparse_vectors WHERE id = ?",
                [(cid,) for cid in ids],
            )
            self._sqlite_conn.commit()

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
                    else ""
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

    def get_collection(self, name: str):
        """
        切换到指定 collection（不改变默认 collection 名）。

        用于跨知识库操作。
        """
        self._ensure_client()
        self._init_sqlite()
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": self._config.hnsw_space},
            embedding_function=_NoOpEmbeddingFunction(),
        )
        return self._collection

    def delete_by_filter(self, where: Dict[str, Any], collection_name: str = None) -> int:
        """
        按元数据条件删除向量（用于按 doc_name 删除文档的所有 chunk）。

        参数:
            where: ChromaDB where 条件，如 {"doc_name": "test"}
            collection_name: 目标 collection（默认用当前配置的）

        返回: 删除的 chunk 数量
        """
        if collection_name:
            self.get_collection(collection_name)
        else:
            self._ensure_collection()

        if self._collection is None or self._collection.count() == 0:
            return 0

        # ChromaDB 没有直接 delete by where，需要先查后删
        results = self._collection.get(where=where)
        ids_to_delete = results.get("ids", [])
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
            # 清 sparse 缓存
            for cid in ids_to_delete:
                self._doc_sparse.pop(cid, None)
            if self._sqlite_conn:
                placeholders = ",".join("?" * len(ids_to_delete))
                self._sqlite_conn.execute(
                    f"DELETE FROM sparse_vectors WHERE id IN ({placeholders})",
                    ids_to_delete,
                )
                self._sqlite_conn.commit()

        return len(ids_to_delete)

    def drop_collection(self, name: str = None) -> None:
        """删除 collection。"""
        self._ensure_client()
        name = name or self._config.collection_name
        try:
            self._client.delete_collection(name)
        except Exception:
            pass
        # 只重置 collection 引用如果是当前 collection
        if self._collection is not None and name == self._config.collection_name:
            self._collection = None
            self._doc_sparse.clear()
            if self._sqlite_conn:
                self._sqlite_conn.execute("DELETE FROM sparse_vectors")
                self._sqlite_conn.commit()

    def collection_exists(self, name: str) -> bool:
        """检查 collection 是否存在。"""
        self._ensure_client()
        return name in [c.name for c in self._client.list_collections()]

