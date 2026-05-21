"""
bge-m3 向量化服务 —— Dense + Sparse 双输出。

用法:
    from embedding import EmbeddingService
    svc = EmbeddingService()

    # Dense only
    dense = svc.encode_dense(["文本1", "文本2"])   # → List[List[float]]  (1024d)

    # Sparse only
    sparse = svc.encode_sparse(["文本1", "文本2"])  # → List[Dict[int, float]]

    # 两者同时
    result = svc.encode(["文本1", "文本2"])
    dense_vecs  = result["dense"]   # → np.ndarray (n, 1024)
    sparse_vecs = result["sparse"]  # → List[Dict[int, float]]

    # 计算混合相似度
    scores = svc.similarity(query_dense, query_sparse, doc_dense, doc_sparse)
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Union

import numpy as np
import torch

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class EmbeddingService:
    """bge-m3 Dense + Sparse 单例服务。"""

    _instance = None
    _model = None
    _tokenizer = None
    _sparse_linear: torch.nn.Linear | None = None
    _device = None

    _LOCAL_DIR = Path(__file__).parent / "models" / "bge-m3"

    # Sparse 向量保留的最大 token 数（top-k 过滤，避免稀疏向量过大）
    SPARSE_TOP_K = 256

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load(self):
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        if self._LOCAL_DIR.exists() and (self._LOCAL_DIR / "config.json").exists():
            print(f"[Embedding] loading bge-m3 from local: {self._LOCAL_DIR}")
            model_path = str(self._LOCAL_DIR)
        else:
            print("[Embedding] loading bge-m3 from HuggingFace")
            model_path = "BAAI/bge-m3"

        self._model = SentenceTransformer(model_path)
        self._tokenizer = self._model.tokenizer

        # 加载 sparse_linear 权重到 backbone
        self._device = str(self._model.device)
        backbone = self._model[0].auto_model
        hidden_size = backbone.config.hidden_size

        sparse_weights = torch.load(
            str(self._LOCAL_DIR / "sparse_linear.pt"),
            map_location=self._device,
            weights_only=True,
        )
        self._sparse_linear = torch.nn.Linear(hidden_size, 1)
        self._sparse_linear.load_state_dict(sparse_weights)
        self._sparse_linear.to(self._device)
        self._sparse_linear.eval()

        print(f"[Embedding] bge-m3 ready (dense + sparse) dim={self.dim}")

    # ── Dense ──────────────────────────────────────────────

    def encode_dense(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        self._load()
        return self._model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=False,
            batch_size=32,
        )

    # ── Sparse ─────────────────────────────────────────────

    def encode_sparse(self, texts: List[str]) -> List[Dict[int, float]]:
        """生成 bge-m3 稀疏词权重向量。每个元素是 {token_id: weight}。"""
        self._load()
        results: List[Dict[int, float]] = []

        for text in texts:
            results.append(self._encode_sparse_one(text))

        return results

    def _encode_sparse_one(self, text: str) -> Dict[int, float]:
        """对单条文本计算稀疏向量。"""
        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=8192,
            padding=False,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        input_ids = inputs["input_ids"][0]  # [seq_len]
        attention_mask = inputs["attention_mask"][0]

        with torch.no_grad():
            backbone = self._model[0].auto_model
            hidden_states = backbone(**inputs).last_hidden_state[0]  # [seq_len, 1024]
            token_weights = self._sparse_linear(hidden_states).squeeze(-1)  # [seq_len]
            token_weights = torch.relu(token_weights)  # 非负
            token_weights = token_weights * attention_mask  # mask padding

        # 相同 token 取最大值，过滤零权重
        sparse_dict: Dict[int, float] = {}
        for tid, weight in zip(input_ids.tolist(), token_weights.tolist()):
            tid = int(tid)
            if weight <= 0:
                continue
            if tid in sparse_dict:
                sparse_dict[tid] = max(sparse_dict[tid], weight)
            else:
                sparse_dict[tid] = weight

        # Top-K 过滤
        if len(sparse_dict) > self.SPARSE_TOP_K:
            top_items = sorted(sparse_dict.items(), key=lambda x: -x[1])[:self.SPARSE_TOP_K]
            sparse_dict = dict(top_items)

        # L2 归一化
        norm = np.sqrt(sum(w * w for w in sparse_dict.values()))
        if norm > 0:
            sparse_dict = {k: v / norm for k, v in sparse_dict.items()}

        return sparse_dict

    # ── 混合编码 ───────────────────────────────────────────

    def encode(self, texts: List[str]) -> Dict[str, object]:
        """同时输出 dense + sparse。"""
        return {
            "dense": self.encode_dense(texts),
            "sparse": self.encode_sparse(texts),
        }

    # ── 相似度 ────────────────────────────────────────────

    def similarity(
        self,
        query_dense: np.ndarray,
        query_sparse: Dict[int, float],
        doc_dense: np.ndarray,
        doc_sparse: Dict[int, float],
        alpha: float = 0.5,
    ) -> float:
        """混合相似度: alpha * dense_cos + (1-alpha) * sparse_dot。"""
        # Dense cosine
        d_score = float(np.dot(query_dense, doc_dense))

        # Sparse dot product (对齐的 token 权重乘积求和)
        s_score = 0.0
        for tid, qw in query_sparse.items():
            dw = doc_sparse.get(tid, 0.0)
            s_score += qw * dw

        return alpha * d_score + (1 - alpha) * s_score

    def batch_similarity(
        self,
        query_dense: np.ndarray,
        query_sparse: Dict[int, float],
        doc_dense: np.ndarray,          # (n, 1024)
        doc_sparse: List[Dict[int, float]],  # [n]
        alpha: float = 0.5,
    ) -> np.ndarray:
        """批量混合相似度。返回 shape (n,) 的分数数组。"""
        d_scores = np.dot(doc_dense, query_dense)  # (n,)

        s_scores = np.zeros(len(doc_sparse))
        for i, ds in enumerate(doc_sparse):
            s = 0.0
            for tid, qw in query_sparse.items():
                s += qw * ds.get(tid, 0.0)
            s_scores[i] = s

        return alpha * d_scores + (1 - alpha) * s_scores

    # ── 检索 ──────────────────────────────────────────────

    def search(
        self,
        query: str,
        doc_dense: np.ndarray,          # (n, 1024)
        doc_sparse: List[Dict[int, float]],  # [n]
        top_k: int = 10,
        alpha: float = 0.5,
    ) -> List[tuple]:
        """混合检索，返回 [(doc_idx, score), ...]。
        使用 score-level 融合：alpha * dense_norm + (1-alpha) * sparse_norm。
        """
        q = self.encode([query])
        qd, qs = q["dense"][0], q["sparse"][0]

        n = len(doc_dense)
        d_scores = np.dot(doc_dense, qd)
        s_scores = np.array([
            sum(qs.get(tid, 0.0) * ds.get(tid, 0.0) for tid in qs)
            for ds in doc_sparse
        ])

        # Z-score 归一化后加权
        d_norm = _safe_zscore(d_scores)
        s_norm = _safe_zscore(s_scores)
        hybrid = alpha * d_norm + (1 - alpha) * s_norm

        top_idx = np.argsort(-hybrid)[:top_k]
        return [(int(i), float(hybrid[i])) for i in top_idx]

    # ── 序列化 ────────────────────────────────────────────

    @staticmethod
    def sparse_to_dict(sparse: Dict[int, float]) -> Dict[str, float]:
        """稀疏向量转为 JSON 可序列化格式。"""
        return {str(k): v for k, v in sparse.items()}

    @staticmethod
    def sparse_from_dict(data: Dict[str, float]) -> Dict[int, float]:
        """从 JSON 恢复稀疏向量。"""
        return {int(k): v for k, v in data.items()}

    # ── 工具 ──────────────────────────────────────────────

    @property
    def dim(self) -> int:
        self._load()
        return self._model.get_embedding_dimension()

    @property
    def tokenizer(self):
        self._load()
        return self._tokenizer


def _safe_zscore(x: np.ndarray) -> np.ndarray:
    """Z-score 归一化，处理常数数组。"""
    std = np.std(x)
    if std < 1e-8:
        return np.zeros_like(x)
    return (x - np.mean(x)) / std


# ── 验证 ──────────────────────────────────────────────────

if __name__ == "__main__":
    svc = EmbeddingService()
    print(f"Dense dim: {svc.dim}")

    texts = [
        "员工加班费按国家规定标准发放：工作日加班按150%发放",
        "公司每年组织员工进行健康体检，体检费用由公司承担",
        "我今天中午吃的麻辣烫",
    ]

    # Dense + Sparse
    result = svc.encode(texts)
    dense = result["dense"]
    sparse = result["sparse"]

    for i, t in enumerate(texts):
        top_tokens = sorted(sparse[i].items(), key=lambda x: -x[1])[:8]
        tokens_str = ", ".join(
            f"{svc.tokenizer.decode([tid])}({w:.2f})" for tid, w in top_tokens
        )
        print(f"\n[{i}] {t[:50]}...")
        print(f"    sparse top: {tokens_str}")

    # 检索测试：稀疏 vs 密集
    query = "加班费怎么计算"
    q = svc.encode([query])
    qd, qs = q["dense"][0], q["sparse"][0]

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")
    print(f"{'Doc':30s}  {'dense':>6s}  {'sparse':>6s}  {'hybrid':>6s}")
    for i in range(3):
        ds = float(np.dot(qd, dense[i]))
        ss = svc.similarity(qd, qs, dense[i], sparse[i], alpha=0.0)
        hs = svc.similarity(qd, qs, dense[i], sparse[i], alpha=0.5)
        print(f"{texts[i][:30]:30s}  {ds:6.3f}  {ss:6.3f}  {hs:6.3f}")

    # 验证：加班费文档应得最高分
    best = max(range(3), key=lambda i: svc.similarity(qd, qs, dense[i], sparse[i]))
    print(f"\nBest match: [{best}] {texts[best][:60]}")

    # 换一个精确匹配的 query
    query2 = "健康体检"
    q2 = svc.encode([query2])
    qd2, qs2 = q2["dense"][0], q2["sparse"][0]
    print(f"\nQuery: {query2}")
    for i in range(3):
        hs = svc.similarity(qd2, qs2, dense[i], sparse[i])
        print(f"  [{i}] hybrid={hs:.3f}  {texts[i][:50]}")
    best2 = max(range(3), key=lambda i: svc.similarity(qd2, qs2, dense[i], sparse[i]))
    print(f"Best match: [{best2}] {texts[best2][:60]}")
    print("\nOK")
