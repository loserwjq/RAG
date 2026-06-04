"""
Reranker 重排模块 — 使用 bge-reranker-v2-m3 对检索结果精排。

作用：
    初检（Dense + Sparse）召回候选集后，用 Cross-Encoder 对 query-doc 对
    进行精细打分，显著提升 top-k 结果的相关性。

用法:
    from rag.reranker import Reranker
    reranker = Reranker()
    scored = reranker.rerank("加班费怎么算", ["文档1内容", "文档2内容"])
    # → [(1, 0.95), (0, 0.32)]  # (原始索引, 分数) 按分数降序
"""

from pathlib import Path
from typing import Dict, List, Tuple

from rag.config import RerankerConfig


class Reranker:
    """bge-reranker-v2-m3 Cross-Encoder 重排器（单例 + 惰性加载）。"""

    _instance = None

    def __new__(cls, config: RerankerConfig = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: RerankerConfig = None):
        if self._initialized:
            return
        self._config = config or RerankerConfig()
        self._model = None
        self._tokenizer = None
        self._initialized = True

    # ── 惰性加载 ──────────────────────────────────────────

    def _load(self):
        if self._model is not None:
            return

        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model_dir = Path(self._config.model_dir)
        if model_dir.exists() and (model_dir / "config.json").exists():
            print(f"[Reranker] loading from local: {model_dir}")
            model_path = str(model_dir)
        else:
            print(f"[Reranker] loading from HuggingFace: {self._config.model_name}")
            model_path = self._config.model_name

        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self._model.eval()

        # 设备
        if self._config.device:
            self._model.to(self._config.device)

        self._device = str(next(self._model.parameters()).device)
        print(f"[Reranker] ready, device={self._device}")

    # ── 重排 ──────────────────────────────────────────────

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = None,
    ) -> List[Tuple[int, float]]:
        """
        对 query-document 对进行重排。

        参数:
            query: 查询文本
            documents: 候选文档列表
            top_k: 返回前 k 个结果（默认全部返回）

        返回: [(原始索引, 分数)] 按分数降序排列
        """
        import torch

        if not documents:
            return []

        self._load()
        top_k = top_k or len(documents)

        # 构建 query-doc 对
        pairs = [[query, doc] for doc in documents]

        # 分批处理
        all_scores = []
        batch_size = self._config.batch_size

        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self._config.max_length,
                return_tensors="pt",
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            with torch.no_grad():
                scores = self._model(**inputs).logits.squeeze(-1)
                # sigmoid 归一化到 [0, 1]
                scores = torch.sigmoid(scores)
                all_scores.extend(scores.cpu().tolist())

        # 按分数降序排列
        indexed_scores = [(i, s) for i, s in enumerate(all_scores)]
        indexed_scores.sort(key=lambda x: -x[1])

        return indexed_scores[:top_k]

    def rerank_results(
        self,
        query: str,
        results: List[Dict],
        top_k: int = None,
    ) -> List[Dict]:
        """
        对检索结果列表进行重排（直接操作 search 返回的 dict 列表）。

        参数:
            query: 查询文本
            results: search() 返回的结果列表 [{content, score, ...}]
            top_k: 返回前 k 个

        返回: 重排后的结果列表，新增 rerank_score 字段
        """
        if not results:
            return []

        documents = [r["content"] for r in results]
        ranked = self.rerank(query, documents, top_k=top_k)

        reranked = []
        for orig_idx, rerank_score in ranked:
            item = dict(results[orig_idx])
            item["rerank_score"] = round(rerank_score, 4)
            item["original_rank"] = orig_idx + 1
            reranked.append(item)

        return reranked
