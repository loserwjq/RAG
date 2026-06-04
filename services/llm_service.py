"""
LLM 微服务 — 大模型生成。

端口: 8004
职责: 文本生成（单次 + 流式）。
"""

import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from services.logger import setup_service
from rag.config import RAGConfig
from rag.llm import LLM

app = FastAPI(title="LLM Service")
logger = setup_service(app, "llm-service")

config = RAGConfig.from_env()
llm = LLM(config.llm)


class GenerateRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class StreamRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    temperature: Optional[float] = None


class RewriteRequest(BaseModel):
    query: str


@app.post("/rewrite")
async def rewrite_query(req: RewriteRequest):
    """检索前问题改写：修正拼写 + 展开缩写。"""
    try:
        rewritten = llm.rewrite_query(req.query)
        logger.info(f"Query rewriting: '{req.query[:60]}' -> '{rewritten[:60]}'")
        return {"rewritten": rewritten, "original": req.query}
    except Exception as e:
        logger.error(f"Query rewriting 失败: {e}")
        return {"rewritten": req.query, "original": req.query, "error": str(e)}


@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        logger.info(f"生成: prompt='{req.prompt[:80]}...'")
        content = llm.generate(
            prompt=req.prompt,
            system=req.system,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        logger.info(f"生成完成: {len(content)} 字符")
        return {"content": content}

    except Exception as e:
        logger.error(f"LLM 生成失败: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.post("/stream")
async def stream(req: StreamRequest):
    logger.info(f"流式生成: prompt='{req.prompt[:80]}...'")

    def generate():
        try:
            for chunk in llm.stream(
                prompt=req.prompt,
                system=req.system,
                temperature=req.temperature,
            ):
                yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"流式生成异常: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
async def health():
    try:
        result = llm.check_health()
        return {
            "status": result.get("status", "unknown"),
            "service": "llm-service",
            "model": llm.model,
            "detail": result,
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {"status": "error", "service": "llm-service", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
