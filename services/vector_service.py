"""
向量微服务 — Embedder + Store。

端口: 8002
职责: 向量化、存储、检索。
支持多 collection 隔离不同知识库。
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from services.logger import setup_service
from rag.config import RAGConfig, StoreConfig
from rag.embedder import Embedder
from rag.store import VectorStore

app = FastAPI(title="Vector Service")
logger = setup_service(app, "vector-service")

config = RAGConfig.from_env()
embedder = None

# 多 collection 实例缓存
_stores: Dict[str, VectorStore] = {}
_display_names: Dict[str, str] = {}  # internal_name → display_name
_default_collection = config.store.collection_name  # "documents"


def _get_store(collection: str) -> VectorStore:
    """获取或创建指定 collection 的 VectorStore。"""
    if collection not in _stores:
        cfg = StoreConfig(
            persist_dir=config.store.persist_dir,
            collection_name=collection,
            hnsw_space=config.store.hnsw_space,
        )
        _stores[collection] = VectorStore(cfg)
        logger.info(f"创建/加载 collection: {collection}")
    return _stores[collection]


@app.on_event("startup")
def startup():
    global embedder
    logger.info("初始化 Embedder...")
    embedder = Embedder(config.embedder)
    # 预热默认 collection
    _get_store(_default_collection)
    logger.info(f"就绪, 默认 collection: {_default_collection}")


class AddRequest(BaseModel):
    texts: List[str]
    metadatas: List[Dict[str, Any]]
    collection: Optional[str] = None
    display_name: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = None
    alpha: Optional[float] = None
    collection: Optional[str] = None


class DeleteRequest(BaseModel):
    ids: List[str]
    collection: Optional[str] = None


class DeleteByDocRequest(BaseModel):
    doc_name: str
    collection: str  # 必须指定 collection，防止误删


@app.post("/add")
async def add(req: AddRequest):
    try:
        coll = req.collection or _default_collection
        if req.display_name and coll not in _display_names:
            _display_names[coll] = req.display_name
        store = _get_store(coll)
        logger.info(f"[{coll}] 向量化 {len(req.texts)} 条文本...")
        vectors = embedder.encode(req.texts)
        dense_vecs = vectors["dense"]
        sparse_vecs = vectors["sparse"]

        logger.info(f"[{coll}] 写入向量库...")
        ids = store.add(
            texts=req.texts,
            dense_vecs=dense_vecs,
            sparse_vecs=sparse_vecs,
            metadatas=req.metadatas,
        )
        logger.info(f"[{coll}] 写入完成: {len(ids)} 条")
        return {"ids": ids, "count": len(ids), "collection": coll}

    except Exception as e:
        logger.error(f"向量化/存储失败: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.post("/search")
async def search(req: SearchRequest):
    try:
        coll = req.collection or _default_collection
        store = _get_store(coll)
        search_cfg = config.search
        if req.top_k:
            search_cfg.top_k = req.top_k
        if req.alpha is not None:
            search_cfg.alpha = req.alpha

        logger.info(f"[{coll}] 检索: '{req.query[:50]}...' top_k={search_cfg.top_k}")
        query_vecs = embedder.encode([req.query])
        query_dense = query_vecs["dense"][0]
        query_sparse = query_vecs["sparse"][0]

        results = store.search(query_dense, query_sparse, search_cfg)
        logger.info(f"[{coll}] 检索完成: {len(results)} 条结果")
        return {"results": results, "collection": coll}

    except Exception as e:
        logger.error(f"检索失败: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.delete("/delete")
async def delete(req: DeleteRequest):
    try:
        coll = req.collection or _default_collection
        store = _get_store(coll)
        store.delete(req.ids)
        logger.info(f"[{coll}] 删除 {len(req.ids)} 条")
        return {"deleted": len(req.ids), "collection": coll}
    except Exception as e:
        logger.error(f"删除失败: {e}", exc_info=True)
        return {"error": str(e)}


@app.post("/delete-by-doc")
async def delete_by_doc(req: DeleteByDocRequest):
    """按文档名删除指定 collection 中的所有相关向量。"""
    try:
        store = _get_store(req.collection)
        count = store.delete_by_filter({"doc_name": req.doc_name})
        logger.info(f"[{req.collection}] 按 doc_name='{req.doc_name}' 删除 {count} 条")
        return {"deleted": count, "collection": req.collection, "doc_name": req.doc_name}
    except Exception as e:
        logger.error(f"按文档删除失败: {e}", exc_info=True)
        return {"error": str(e)}


@app.delete("/collection/{name}")
async def drop_collection(name: str):
    """删除整个 collection。"""
    try:
        store = _get_store(_default_collection)
        store.drop_collection(name)
        if name in _stores:
            del _stores[name]
        _display_names.pop(name, None)
        logger.info(f"删除 collection: {name}")
        return {"deleted": name}
    except Exception as e:
        logger.error(f"删除 collection 失败: {e}", exc_info=True)
        return {"error": str(e)}


@app.get("/collections")
async def list_collections():
    """列出所有 collection 及其文档数。"""
    store = _get_store(_default_collection)
    names = store.list_collections()
    result = []
    for name in names:
        s = _get_store(name)
        display = _display_names.get(name, name)
        result.append({"name": name, "display_name": display, "count": s.count})
    return {"collections": result}


@app.get("/info")
async def info():
    store = _get_store(_default_collection)
    return {
        "doc_count": store.count,
        "collection": _default_collection,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "vector-service",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
