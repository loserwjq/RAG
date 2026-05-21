"""
RAG Pipeline — 分层解耦架构。

模块:
    config   - 统一配置管理
    parser   - 文件解析 (PDF/MD → content_list)
    chunker  - 智能语义切块
    embedder - bge-m3 向量化 (Dense + Sparse)
    store    - ChromaDB 向量库
    pipeline - 编排层，串联各组件
"""

from rag.pipeline import Pipeline

__all__ = ["Pipeline"]
