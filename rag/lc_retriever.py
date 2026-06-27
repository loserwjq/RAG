"""
LangChain Retriever 适配器 — 混合检索（Dense + Sparse Hybrid Search）。

这是 NeuralKB 系统的核心区分器。标准 LangChain Chroma Retriever 只支持
单向量相似度检索，本模块实现完整的混合检索流程：

    1. Dense ANN 检索（ChromaDB HNSW index）
    2. Sparse 重打分（BGE-M3 lexical vectors）
    3. Z-score 归一化 + 加权融合（alpha=0.5）

用法:
    from rag.lc_retriever import HybridRetriever
    from rag.store import VectorStore
    from rag.embedder import Embedder
    from rag.config import StoreConfig, EmbedderConfig, SearchConfig

    store = VectorStore(StoreConfig())
    embedder = Embedder(EmbedderConfig())
    retriever = HybridRetriever(
        store=store,
        embedder=embedder,
        search_config=SearchConfig(top_k=5),
    )
    docs = retriever.invoke("查询文本")
"""

from typing import Dict, List, Optional

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from rag.config import SearchConfig


class HybridRetriever(BaseRetriever):
    """基于 Hybrid Dense+Sparse 搜索的自定义 LangChain Retriever。

    组合在 LCEL 链中:
        retriever = HybridRetriever(store=store, embedder=embedder)
        chain = {"context": retriever, "question": RunnablePassthrough()} | prompt | llm
    """

    store: object  # rag.store.VectorStore
    embedder: object  # rag.embedder.Embedder
    search_config: SearchConfig = SearchConfig()

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        """执行混合检索并返回 LangChain Document 列表。

        参数:
            query: 查询文本

        返回: 按混合分数降序排列的 Document 列表
        """
        # Step 1: 编码查询（dense + sparse）
        encoded = self.embedder.encode([query])
        q_dense = encoded["dense"][0]
        q_sparse = encoded["sparse"][0]

        # Step 2: 混合检索
        results = self.store.search(q_dense, q_sparse, self.search_config)

        # Step 3: 转换为 LangChain Document 列表
        docs = []
        for r in results:
            meta = dict(r.get("metadata", {}))
            # 将分数也存入 metadata（保留完整信息）
            meta["score"] = r.get("score", 0)
            meta["dense_score"] = r.get("dense_score")
            meta["sparse_score"] = r.get("sparse_score")
            meta["chunk_id"] = r.get("id", "")

            docs.append(Document(
                page_content=r.get("content", ""),
                metadata=meta,
            ))

        return docs

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager=None,
    ) -> List[Document]:
        """异步版本（委托给同步实现）。"""
        return self._get_relevant_documents(query, run_manager=run_manager)
