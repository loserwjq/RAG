"""
向量化模块 — bge-m3 Dense + Sparse 双输出。

职责单一：文本 → 向量。
单例模式：模型只加载一次，全局复用。
异常隔离：加载失败时抛出明确异常，不影响其他模块。
"""

import os
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch

from rag.config import EmbedderConfig

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class Embedder:
    """bge-m3 Dense + Sparse 向量化服务（单例）。"""

    _instance = None

    def __new__(cls, config: EmbedderConfig = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: EmbedderConfig = None):
        if self._initialized:
            return
        self._config = config or EmbedderConfig()
        self._model = None
        self._tokenizer = None
        self._sparse_linear = None
        self._device = None
        self._initialized = True

    # ── 惰性加载 ──────────────────────────────────────────

    def _load(self):
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        model_dir = Path(self._config.model_dir)
        if model_dir.exists() and (model_dir / "config.json").exists():
            print(f"[Embedder] loading bge-m3 from local: {model_dir}")
            model_path = str(model_dir)
        else:
            print(f"[Embedder] loading bge-m3 from HuggingFace: {self._config.model_name}")
            model_path = self._config.model_name

        self._model = SentenceTransformer(model_path)
        self._tokenizer = self._model.tokenizer
        self._device = str(self._model.device)

        # 加载 sparse_linear 权重
        backbone = self._model[0].auto_model
        hidden_size = backbone.config.hidden_size

        sparse_path = model_dir / "sparse_linear.pt"
        if not sparse_path.exists():
            raise FileNotFoundError(f"sparse_linear.pt not found: {sparse_path}")

        sparse_weights = torch.load(
            str(sparse_path),
            map_location=self._device,
            weights_only=True,
        )
        self._sparse_linear = torch.nn.Linear(hidden_size, 1)
        self._sparse_linear.load_state_dict(sparse_weights)
        self._sparse_linear.to(self._device)
        self._sparse_linear.eval()

        print(f"[Embedder] ready (dense={self.dim}d + sparse) device={self._device}")

    # ── Dense 编码 ────────────────────────────────────────

    def encode_dense(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        """批量 Dense 编码，返回 (n, dim) 的 numpy 数组。"""
        self._load()
        return self._model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=False,
            batch_size=self._config.batch_size,
        )

    # ── Sparse 编码 ───────────────────────────────────────

    def encode_sparse(self, texts: List[str]) -> List[Dict[int, float]]:
        """批量 Sparse 编码，返回 [{token_id: weight}, ...]。"""
        self._load()
        return [self._encode_sparse_one(text) for text in texts]

    def _encode_sparse_one(self, text: str) -> Dict[int, float]:
        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=self._config.max_length,
            padding=False,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        input_ids = inputs["input_ids"][0]
        attention_mask = inputs["attention_mask"][0]

        with torch.no_grad():
            backbone = self._model[0].auto_model
            hidden_states = backbone(**inputs).last_hidden_state[0]
            token_weights = self._sparse_linear(hidden_states).squeeze(-1)
            token_weights = torch.relu(token_weights)
            token_weights = token_weights * attention_mask

        # 相同 token 取最大值
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
        if len(sparse_dict) > self._config.sparse_top_k:
            top_items = sorted(sparse_dict.items(), key=lambda x: -x[1])[:self._config.sparse_top_k]
            sparse_dict = dict(top_items)

        # L2 归一化
        norm = np.sqrt(sum(w * w for w in sparse_dict.values()))
        if norm > 0:
            sparse_dict = {k: v / norm for k, v in sparse_dict.items()}

        return sparse_dict

    # ── 混合编码 ──────────────────────────────────────────

    def encode(self, texts: List[str]) -> Dict[str, object]:
        """同时输出 dense + sparse。"""
        return {
            "dense": self.encode_dense(texts),
            "sparse": self.encode_sparse(texts),
        }

    # ── 属性 ──────────────────────────────────────────────

    @property
    def dim(self) -> int:
        self._load()
        return self._model.get_embedding_dimension()

    @property
    def tokenizer(self):
        self._load()
        return self._tokenizer

    # ── 序列化工具 ────────────────────────────────────────

    @staticmethod
    def sparse_to_json(sparse: Dict[int, float]) -> Dict[str, float]:
        """稀疏向量转为 JSON 可序列化格式。"""
        return {str(k): v for k, v in sparse.items()}

    @staticmethod
    def sparse_from_json(data: Dict[str, float]) -> Dict[int, float]:
        """从 JSON 恢复稀疏向量。"""
        return {int(k): v for k, v in data.items()}
