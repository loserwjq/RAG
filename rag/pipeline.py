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
from rag.reranker import Reranker
from rag.llm import LLM, LLMError


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
        self._reranker = Reranker(self._config.reranker) if self._config.reranker.enabled else None
        self._llm = LLM(self._config.llm)

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
        rerank: bool = True,
        rewrite_query: bool = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索: (Query Rewriting) → Dense + Sparse 召回 → Reranker 精排。

        参数:
            query: 查询文本
            top_k: 最终返回结果数（默认用配置值）
            alpha: dense 权重（默认用配置值）
            rerank: 是否使用 Reranker 重排（默认 True）
            rewrite_query: 是否 LLM 改写问题（默认跟随配置）

        返回: [{id, content, score, metadata, dense_score, sparse_score, rerank_score?}]
        """
        from rag.config import SearchConfig

        t_total = time.time()
        final_top_k = top_k or self._config.search.top_k

        # Step 0: LLM Query Rewriting（修正拼写 + 扩展语义）
        do_rewrite = rewrite_query if rewrite_query is not None else self._config.llm.rewrite_enabled
        search_query = query
        if do_rewrite:
            t0 = time.time()
            rewritten = self._llm.rewrite_query(query)
            if rewritten and rewritten != query:
                search_query = rewritten
                print(f"[Pipeline.search] [timer]Query rewritten: \"{query}\" -> \"{rewritten}\" ({time.time() - t0:.2f}s)")

        # 编码 query
        t0 = time.time()
        q = self._embedder.encode([search_query])
        qd, qs = q["dense"][0], q["sparse"][0]
        t_encode = time.time() - t0
        print(f"[Pipeline.search] [timer]Query 编码: {t_encode:.2f}s")

        # 初检：召回更多候选（reranker 需要更大候选集）
        recall_k = final_top_k * 3 if (rerank and self._reranker) else final_top_k
        search_cfg = SearchConfig(
            top_k=recall_k,
            alpha=alpha if alpha is not None else self._config.search.alpha,
            candidate_multiplier=self._config.search.candidate_multiplier,
        )

        t0 = time.time()
        results = self._store.search(qd, qs, search_cfg)
        t_search = time.time() - t0
        print(f"[Pipeline.search] [timer]向量库检索: {t_search:.2f}s")

        # Reranker 精排
        if rerank and self._reranker and results:
            t0 = time.time()
            results = self._reranker.rerank_results(query, results, top_k=final_top_k)
            t_rerank = time.time() - t0
            print(f"[Pipeline.search] [timer]Reranker 精排: {t_rerank:.2f}s")
        else:
            results = results[:final_top_k]

        print(f"[Pipeline.search] [timer]检索总耗时: {time.time() - t_total:.2f}s")
        return results

    # ── 问答 ──────────────────────────────────────────────

    def ask(
        self,
        question: str,
        top_k: int = 5,
        alpha: float = None,
        stream: bool = False,
        rewrite_query: bool = None,
    ) -> Dict[str, Any]:
        """
        检索增强问答 (RAG QA)。

        流程: Query Rewriting → 检索 top_k → 构建上下文 → LLM 生成答案

        参数:
            question: 用户问题
            top_k: 检索文档数
            alpha: dense/sparse 权重
            stream: 是否流式输出（True 时 answer 为 generator）
            rewrite_query: 是否 LLM 改写问题（默认跟随配置）

        返回: {answer, sources: [{content, score, metadata}]}
        """
        # Step 1: 检索相关文档
        results = self.search(question, top_k=top_k, alpha=alpha, rewrite_query=rewrite_query)

        if not results:
            return {
                "answer": "未找到相关文档，无法回答。",
                "sources": [],
            }

        # Step 2: 构建上下文
        context = self._build_context(results)

        # Step 3: LLM 生成答案
        try:
            if stream:
                answer = self._llm.stream_with_context(question, context)
            else:
                answer = self._llm.answer_with_context(question, context)
        except LLMError as e:
            answer = f"[LLM 错误] {e}"

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
            doc_name = r.get("metadata", {}).get("doc_name", f"文档{i}")
            parts.append(f"[参考文档: {doc_name}] (相关度: {r['score']:.3f})\n{r['content']}")
        return "\n\n---\n\n".join(parts)

    # ── LLM 健康检查 ─────────────────────────────────────

    def check_llm(self) -> Dict[str, Any]:
        """检查 LLM 服务状态。"""
        return self._llm.check_health()

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
