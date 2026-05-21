"""
向量数据库对接 —— ChromaDB（嵌入式，无需服务端）。

用法:
    from vector_store import VectorStore

    store = VectorStore("./chroma_db")
    store.add(chunks, embeddings, metadatas)

    results = store.search("员工加班费怎么算", top_k=5)
    for r in results:
        print(r["content"], r["score"], r["metadata"])
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Windows DLL 加载顺序: sentence_transformers 必须在 chromadb 之前导入
from sentence_transformers import SentenceTransformer

import numpy as np


class _NoOpEmbeddingFunction:
    """禁用 ChromaDB 自带 embedding —— 我们使用外部 bge-m3。"""
    def __call__(self, input):
        raise RuntimeError("ChromaDB built-in embedding disabled — use external bge-m3 embeddings")


class VectorStore:
    """ChromaDB 向量库，存储 dense + sparse + metadata。"""

    def __init__(self, persist_dir: str = "./chroma_db"):
        # Windows DLL 加载顺序要求: sentence_transformers 先于 chromadb 导入
        from embedding import EmbeddingService  # noqa: F811
        import chromadb
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = None
        self._embedding_svc = None
        self._doc_sparse: Dict[str, Dict[int, float]] = {}  # id → sparse vector
        self._doc_text: Dict[str, str] = {}                  # id → full text

    # ── CRUD ──────────────────────────────────────────────

    def create_collection(self, name: str = "documents") -> None:
        """创建或获取 collection。不启用 ChromaDB 自带 embedding。"""
        try:
            self._collection = self._client.get_collection(
                name=name,
                embedding_function=_NoOpEmbeddingFunction(),
            )
        except Exception:
            self._collection = self._client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=_NoOpEmbeddingFunction(),
            )

    def add(
        self,
        texts: List[str],
        embeddings: np.ndarray,               # (n, 1024)  dense
        sparse_vecs: List[Dict[int, float]],   # [n]       sparse
        metadatas: List[Dict[str, Any]],       # [n]
        ids: Optional[List[str]] = None,       # [n]       ID
    ) -> List[str]:
        """批量写入。返回 id 列表。
        注意: 调用前须确保 sentence_transformers 已先于 chromadb 导入，
        否则 Windows 上 onnxruntime DLL 加载顺序会导致 segfault。
        """
        if self._collection is None:
            self.create_collection()

        n = len(texts)
        if ids is None:
            ids = [f"chunk_{self._collection.count() + i}" for i in range(n)]

        # ChromaDB: 每个 chunk 一条记录
        self._collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

        # 本地存储 sparse + 完整文本
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
        query: str,
        top_k: int = 10,
        alpha: float = 0.5,
        embedding_svc=None,  # EmbeddingService, 惰性加载
    ) -> List[Dict[str, Any]]:
        """
        混合检索: dense(ChromaDB) + sparse(local re-score)。

        返回: [{id, content, score, metadata, dense_score, sparse_score}]
        """
        if self._collection is None or self._collection.count() == 0:
            return []

        # 获取 embedding service
        if embedding_svc is None:
            if self._embedding_svc is None:
                from embedding import EmbeddingService
                self._embedding_svc = EmbeddingService()
            embedding_svc = self._embedding_svc

        # 编码 query
        q = embedding_svc.encode([query])
        qd, qs = q["dense"][0], q["sparse"][0]

        # 1. Dense 检索: ChromaDB 取 top-K*3 候选
        n_candidates = min(top_k * 3, self._collection.count())
        dense_results = self._collection.query(
            query_embeddings=[qd.tolist()],
            n_results=n_candidates,
            include=["documents", "metadatas", "distances"],
        )

        # 2. Sparse 重打分
        ids_candidate = dense_results["ids"][0]
        distances = dense_results["distances"][0]   # cosine distance: 0=best, 2=worst

        d_scores = np.array([1.0 - d / 2.0 for d in distances])  # → cosine similarity

        s_scores = np.zeros(len(ids_candidate))
        for i, cid in enumerate(ids_candidate):
            sparse = self._doc_sparse.get(cid, {})
            s_scores[i] = sum(qs.get(tid, 0.0) * sparse.get(tid, 0.0) for tid in qs)

        # Z-score 归一化 + 加权
        d_norm = _safe_zscore(d_scores)
        s_norm = _safe_zscore(s_scores)
        hybrid = alpha * d_norm + (1 - alpha) * s_norm

        # 排序取 top_k
        top_idx = np.argsort(-hybrid)[:top_k]

        results = []
        for i in top_idx:
            cid = ids_candidate[i]
            results.append({
                "id": cid,
                "content": dense_results["documents"][0][i] if dense_results["documents"] else self._doc_text.get(cid, ""),
                "score": round(float(hybrid[i]), 4),
                "dense_score": round(float(d_scores[i]), 4),
                "sparse_score": round(float(s_scores[i]), 4),
                "metadata": dense_results["metadatas"][0][i] if dense_results["metadatas"] else {},
            })

        return results

    # ── 批量导入 ──────────────────────────────────────────

    def import_chunks(
        self,
        chunks_path: str,
        doc_name: str = "",
    ) -> int:
        """
        从 _chunks.json 文件批量导入。

        返回导入的 chunk 数量。
        """
        from embedding import EmbeddingService

        data = json.loads(Path(chunks_path).read_text(encoding="utf-8"))
        texts, metadatas, sparse_vecs = [], [], []

        svc = EmbeddingService()
        print(f"编码 {len(data)} chunks...")

        for i, chunk in enumerate(data):
            ctype = chunk.get("type", "text")
            text = chunk.get("text", "")
            if not text.strip():
                continue

            texts.append(text)
            metadatas.append({
                "doc_name": doc_name,
                "type": ctype,
                "page_idx": chunk.get("page_idx", 0),
                "chunk_idx": i,
            })

        # 批量编码
        dense = svc.encode_dense(texts)
        sparse_vecs = svc.encode_sparse(texts)

        # 写入
        ids = self.add(texts, dense, sparse_vecs, metadatas)
        print(f"导入完成: {len(ids)} chunks → {self._collection.name}")
        return len(ids)

    # ── 工具 ──────────────────────────────────────────────

    @property
    def count(self) -> int:
        return self._collection.count() if self._collection else 0

    def list_collections(self) -> List[str]:
        return [c.name for c in self._client.list_collections()]

    def drop_collection(self, name: str = "documents") -> None:
        try:
            self._client.delete_collection(name)
            self._collection = None
            self._doc_sparse.clear()
            self._doc_text.clear()
        except Exception:
            pass


def _safe_zscore(x: np.ndarray) -> np.ndarray:
    std = np.std(x)
    if std < 1e-8:
        return np.zeros_like(x)
    return (x - np.mean(x)) / std


# ── 验证 ──────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    store = VectorStore("./chroma_db")

    # 导入 test.md 的 chunks
    chunk_file = "output/test/auto/test_chunks.json"
    if Path(chunk_file).exists():
        print("导入 chunks...")
        n = store.import_chunks(chunk_file, doc_name="云图数字员工手册")
        print(f"已导入 {n} chunks\n")

        # 测试检索
        queries = ["员工加班费怎么算", "请假流程", "离职提前多久通知", "绩效考核不合格后果"]
        for q in queries:
            results = store.search(q, top_k=3)
            print(f"\n查询: {q}")
            for r in results:
                # 显示最末级标题
                headings = [l.strip('# ').strip() for l in r["content"].split("\n") if l.startswith('#')]
                section = ' > '.join(headings[-3:]) if headings else r["content"][:80]
                print(f"  {r['score']:+.3f}  [{r['id']}] {section}")

        # 清理
        store.drop_collection()
        print("\n验证通过")
    else:
        print(f"请先运行 run_with_chunking.py test.md 生成 {chunk_file}")
