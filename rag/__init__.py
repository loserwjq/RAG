"""
RAG Pipeline — 分层解耦架构，支持多用户知识库。

模块:
    config     - 统一配置管理
    database   - SQLite 业务数据库（用户、知识库、文档记录）
    auth       - 用户认证（密码哈希 + JWT / Dev Mode）
    parser     - 文件解析 (PDF/DOCX/PPTX/XLSX/MD/图片)
    chunker    - 智能语义切块
    embedder   - bge-m3 向量化 (Dense + Sparse)
    store      - ChromaDB 向量库
    reranker   - bge-reranker-v2-m3 精排
    llm        - OpenAI 兼容 API (Gitee AI Qwen3)
    kb_manager - 知识库业务逻辑（跨 DB + ChromaDB）
    pipeline   - 编排层，串联各组件
    main       - CLI 入口

用法:
    python -m rag init-db                          # 初始化数据库
    python -m rag ingest test.md --kb 1            # 入库到知识库
    python -m rag search "关键词" --kb 1            # 检索
"""


def __getattr__(name):
    """惰性导入，避免 import rag 时立即加载重型依赖。"""
    _lazy = {
        "Pipeline": "rag.pipeline",
        "Database": "rag.database",
        "KBManager": "rag.kb_manager",
        "AuthManager": "rag.auth",
    }
    if name in _lazy:
        import importlib
        module_path, _, attr = _lazy[name].rpartition(".")
        module = importlib.import_module(module_path)
        return getattr(module, attr)
    raise AttributeError(f"module 'rag' has no attribute {name!r}")


__all__ = [
    "Pipeline", "Database", "KBManager", "AuthManager",
]
