"""
LangChain Reranker 适配器 — 将 BGE-Reranker-v2-M3 封装为 LCEL Runnable。

用法:
    from rag.lc_reranker import create_reranker_runnable, rerank_documents
    from rag.reranker import Reranker

    reranker = Reranker()
    # 方式 1: 作为独立函数
    reranked_docs = rerank_documents(reranker, "查询", docs)

    # 方式 2: 作为 LCEL Runnable（可嵌入链中）
    step = create_reranker_runnable(reranker)
    chain = retriever | step
"""

from typing import List

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda


def rerank_documents(
    reranker: object,  # rag.reranker.Reranker
    query: str,
    documents: List[Document],
    top_k: int = None,
) -> List[Document]:
    """使用 Reranker 对 Document 列表重排。

    参数:
        reranker: Reranker 实例
        query: 查询文本
        documents: 候选 Document 列表
        top_k: 返回前 k 个（默认全部返回）

    返回: 重排后的 Document 列表（新增 rerank_score + original_rank 到 metadata）
    """
    if not reranker or not documents:
        return documents[:top_k] if top_k else documents

    contents = [d.page_content for d in documents]
    ranked = reranker.rerank(query, contents, top_k=top_k)

    result = []
    for orig_idx, score in ranked:
        doc = documents[orig_idx]
        doc.metadata["rerank_score"] = round(score, 4)
        doc.metadata["original_rank"] = orig_idx + 1
        result.append(doc)

    return result


def create_reranker_runnable(reranker: object):
    """创建一个 LCEL Runnable，用于对检索结果重排。

    返回的 Runnable 接受 {"query": str, "documents": List[Document]} 作为输入，
    输出重排后的 List[Document]。

    用法:
        step = create_reranker_runnable(reranker)
        chain = retriever | (lambda docs: {"documents": docs, "query": query}) | step
    """
    def _rerank(inputs: dict) -> List[Document]:
        query = inputs.get("query", "") if isinstance(inputs, dict) else ""
        documents = inputs.get("documents", []) if isinstance(inputs, dict) else inputs
        if isinstance(inputs, list):
            # 如果直接传入 Document 列表，需要从上下文获取 query
            # 这种用法需要配合 RunnablePassthrough 使用
            documents = inputs
            query = ""

        if not reranker or not documents:
            return documents

        contents = [d.page_content for d in documents]
        ranked = reranker.rerank(query, contents)

        result = []
        for orig_idx, score in ranked:
            doc = documents[orig_idx]
            doc.metadata["rerank_score"] = round(score, 4)
            doc.metadata["original_rank"] = orig_idx + 1
            result.append(doc)

        return result

    return RunnableLambda(_rerank)
