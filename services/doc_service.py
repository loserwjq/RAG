"""
文档处理微服务 — Parser + Chunker。

端口: 8001
职责: 接收文件路径，解析并切块，返回 chunks。
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from services.logger import setup_service
from rag.config import RAGConfig
from rag.parser import get_parser
from rag.chunker import Chunker
from pathlib import Path

app = FastAPI(title="Doc Service")
logger = setup_service(app, "doc-service")

config = RAGConfig.from_env()
chunker = Chunker(config.chunker)


class ParseRequest(BaseModel):
    file_path: str
    doc_name: Optional[str] = None


@app.post("/parse")
async def parse(req: ParseRequest):
    file_path = Path(req.file_path)
    doc_name = req.doc_name or file_path.stem

    if not file_path.exists():
        logger.error(f"文件不存在: {file_path}")
        return {"error": f"文件不存在: {file_path}"}, 400

    try:
        logger.info(f"开始解析: {file_path.name}")
        parser = get_parser(file_path, config.parser)
        content_list = parser.parse(file_path)
        logger.info(f"解析完成: {len(content_list)} blocks")

        logger.info(f"开始切块...")
        chunks = chunker.chunk(content_list)
        logger.info(f"切块完成: {len(chunks)} chunks")

        result_chunks = []
        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            if not text.strip():
                continue
            result_chunks.append({
                "text": text,
                "metadata": {
                    "doc_name": doc_name,
                    "chunk_idx": i,
                    "page_idx": chunk.get("page_idx", 0),
                    "type": chunk.get("type", "text"),
                },
            })

        return {"chunks": result_chunks, "count": len(result_chunks)}

    except Exception as e:
        logger.error(f"文档处理失败: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "doc-service"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
