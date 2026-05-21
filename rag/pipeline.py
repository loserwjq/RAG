"""
编排层 — 串联 Parser → Chunker → Embedder → Store → Search → QA。

Pipeline 是唯一的「胶水层」，各组件通过配置注入，互不依赖。
上层只需调用 Pipeline 的方法，无需了解内部组件细节。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from rag.config import RAGConfig
from rag.parser import get_parser
from rag.chunker import Chunker, count_chars
from rag.embedder import Embedder
from rag.store import VectorStore


class Pipeline:
    """RAG 全流程编排。

    用法:
        from rag import Pipeline

        pipe = Pipeline()
        pipe.ingest("test.md")                    # 解析 + 切块 + 向量化 + 存储
        results = pipe.search("加班费怎么算")      # 混合检索
        answer = pipe.ask("加班费怎么算")          # 检索 + 问答（待接入 LLM）
    """

    def __init__(self, config: RAGConfig = None):
        self._config = config or RAGConfig.from_env()
        self._chunker = Chunker(self._config.chunker)
        self._embedder = Embedder(self._config.embedder)
        self._store = VectorStore(self._config.store)

    # ── 文档入库 ──────────────────────────────────────────

    def ingest(
        self,
        file_path: str,
        doc_name: str = "",
        save_chunks: bool = True,
    ) -> Dict[str, Any]:
        """
        完整入库流程: 解析 → 切块 → 向量化 → 存储。

        参数:
            file_path: 文件路径 (PDF/MD/TXT)
            doc_name: 文档名称（用于 metadata），默认取文件名
            save_chunks: 是否保存切块 JSON 文件

        返回: {doc_name, n_chunks, n_stored, elapsed}
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        doc_name = doc_name or path.stem
        t_start = time.time()

        # Step 1: 解析
        parser = get_parser(path, self._config.parser)
        content_list = parser.parse(path)

        # Step 2: 切块
        chunks = self._chunker.chunk(content_list)
        text_chunks = [c for c in chunks if c.get("type") == "text"]
        print(f"[Pipeline] 切块: {len(content_list)} blocks → {len(text_chunks)} text chunks")

        if not text_chunks:
            print("[Pipeline] 警告: 无文本 chunk 可入库")
            return {"doc_name": doc_name, "n_chunks": 0, "n_stored": 0, "elapsed": 0}

        # 保存切块结果
        if save_chunks:
            self._save_chunks(chunks, path, doc_name)

        # Step 3: 向量化
        texts = [c["text"] for c in text_chunks]
        print(f"[Pipeline] 向量化 {len(texts)} chunks...")

        t0 = time.time()
        dense_vecs = self._embedder.encode_dense(texts)
        sparse_vecs = self._embedder.encode_sparse(texts)
        t_embed = time.time() - t0
        print(f"[Pipeline] 向量化完成 ({t_embed:.1f}s)")

        # Step 4: 存储
        metadatas = [{
            "doc_name": doc_name,
            "type": c.get("type", "text"),
            "page_idx": c.get("page_idx", 0),
            "chunk_idx": i,
        } for i, c in enumerate(text_chunks)]

        ids = self._store.add(texts, dense_vecs, sparse_vecs, metadatas)
        elapsed = time.time() - t_start
        print(f"[Pipeline] 入库完成: {len(ids)} chunks ({elapsed:.1f}s)")

        return {
            "doc_name": doc_name,
            "n_chunks": len(chunks),
            "n_stored": len(ids),
            "elapsed": round(elapsed, 1),
        }

    # ── 检索 ──────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = None,
        alpha: float = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索: Dense + Sparse score-level 融合。

        参数:
            query: 查询文本
            top_k: 返回结果数（默认用配置值）
            alpha: dense 权重（默认用配置值）

        返回: [{id, content, score, metadata, dense_score, sparse_score}]
        """
        from rag.config import SearchConfig

        # 编码 query
        q = self._embedder.encode([query])
        qd, qs = q["dense"][0], q["sparse"][0]

        # 构建检索配置
        search_cfg = SearchConfig(
            top_k=top_k or self._config.search.top_k,
            alpha=alpha if alpha is not None else self._config.search.alpha,
            candidate_multiplier=self._config.search.candidate_multiplier,
        )

        return self._store.search(qd, qs, search_cfg)

    # ── 问答（预留接口，待接入 LLM）─────────────────────────

    def ask(
        self,
        question: str,
        top_k: int = 5,
        alpha: float = None,
    ) -> Dict[str, Any]:
        """
        检索增强问答 (RAG QA)。

        流程: query → 检索 top_k → 构建 prompt → LLM 生成答案

        参数:
            question: 用户问题
            top_k: 检索文档数
            alpha: dense/sparse 权重

        返回: {answer, sources: [{content, score, metadata}]}

        TODO: 接入 LLM（OpenAI / 本地模型）
        """
        # Step 1: 检索相关文档
        results = self.search(question, top_k=top_k, alpha=alpha)

        if not results:
            return {
                "answer": "未找到相关文档，无法回答。",
                "sources": [],
            }

        # Step 2: 构建上下文
        context = self._build_context(results)

        # Step 3: 生成答案（当前为占位实现）
        answer = self._generate_answer(question, context)

        return {
            "answer": answer,
            "sources": [{
                "content": r["content"][:200],
                "score": r["score"],
                "metadata": r["metadata"],
            } for r in results],
        }

    def _build_context(self, results: List[Dict]) -> str:
        """将检索结果拼接为 LLM 上下文。"""
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(f"[文档{i}] (相关度: {r['score']:.3f})\n{r['content']}")
        return "\n\n---\n\n".join(parts)

    def _generate_answer(self, question: str, context: str) -> str:
        """
        LLM 生成答案（占位实现）。

        TODO: 替换为实际 LLM 调用:
            - OpenAI API (GPT-4 / GPT-3.5)
            - 本地模型 (Qwen / ChatGLM / Llama)
            - vLLM / Ollama 等推理框架
        """
        # 占位: 返回检索到的最相关内容摘要
        prompt = f"""基于以下参考文档回答用户问题。如果文档中没有相关信息，请说明无法回答。

参考文档:
{context}

用户问题: {question}

请回答:"""

        # TODO: 替换为 LLM 调用
        # response = llm.generate(prompt)
        # return response

        return f"[待接入LLM] 已检索到相关文档，问题: {question}\n\n最相关内容:\n{context[:500]}..."

    # ── 工具方法 ──────────────────────────────────────────

    def _save_chunks(self, chunks: List[Dict], file_path: Path, doc_name: str) -> Path:
        """保存切块结果到 JSON。"""
        output_dir = Path(self._config.parser.output_dir) / doc_name / "auto"
        output_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = output_dir / f"{doc_name}_chunks.json"
        chunk_path.write_text(
            json.dumps(chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[Pipeline] 切块已保存: {chunk_path}")
        return chunk_path

    @property
    def store(self) -> VectorStore:
        """暴露 store 供高级操作。"""
        return self._store

    @property
    def embedder(self) -> Embedder:
        """暴露 embedder 供高级操作。"""
        return self._embedder

    @property
    def doc_count(self) -> int:
        """当前向量库中的文档数。"""
        return self._store.count
