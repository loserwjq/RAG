"""
Reranker 微服务 — Cross-Encoder 重排。

端口: 8003
职责: 对检索结果进行精排。
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from services.logger import setup_service
from rag.config import RAGConfig
from rag.reranker import Reranker

app = FastAPI(title="Reranker Service")
logger = setup_service(app, "reranker-service")

config = RAGConfig.from_env()
reranker = None


@app.on_event("startup")
def startup():
    global reranker
    if config.reranker.enabled:
        logger.info("初始化 Reranker...")
        reranker = Reranker(config.reranker)
        logger.info("Reranker 就绪")
    else:
        logger.info("Reranker 未启用 (config.reranker.enabled=False)")


class RerankRequest(BaseModel):
    query: str
    documents: List[Dict[str, Any]]
    top_k: Optional[int] = None


@app.post("/rerank")
async def rerank(req: RerankRequest):
    if not config.reranker.enabled or reranker is None:
        logger.info("Reranker 未启用，直接返回原始结果")
        return {"results": req.documents[:req.top_k] if req.top_k else req.documents}

    try:
        logger.info(f"重排: query='{req.query[:50]}...' docs={len(req.documents)}")
        results = reranker.rerank_results(
            query=req.query,
            results=req.documents,
            top_k=req.top_k,
        )
        logger.info(f"重排完成: {len(results)} 条结果")
        return {"results": results}

    except Exception as e:
        logger.error(f"重排失败: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "reranker-service",
        "enabled": config.reranker.enabled,
        "model_loaded": reranker is not None and reranker._model is not None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
