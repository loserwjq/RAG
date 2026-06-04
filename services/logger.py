"""
统一日志模块 — 所有微服务共用。

功能：
- 结构化日志格式（带时间、服务名、级别、请求ID）
- FastAPI 中间件自动记录请求耗时
- 异常处理器记录完整 traceback
- X-Request-ID 跨服务追踪
"""

import logging
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from pathlib import Path

# 强制 stdout/stderr 使用 UTF-8，解决 Windows GBK 编码无法输出日文特殊字符（如・）的问题
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


class ServiceFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__()

    def format(self, record):
        rid = request_id_var.get("-")
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        ms = int(record.created * 1000) % 1000
        level = record.levelname
        msg = record.getMessage()
        base = f"[{ts}.{ms:03d}] [{self.service_name}] [{level}] [{rid}] {msg}"
        if record.exc_info and record.exc_info[0]:
            base += "\n" + "".join(traceback.format_exception(*record.exc_info))
        return base


def setup_logger(service_name: str) -> logging.Logger:
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = ServiceFormatter(service_name)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    error_file = LOG_DIR / f"{service_name}-error.log"
    file_handler = logging.FileHandler(error_file, encoding="utf-8")
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def setup_service(app: FastAPI, service_name: str) -> logging.Logger:
    """为 FastAPI 应用配置日志中间件和异常处理。"""
    logger = setup_logger(service_name)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request_id_var.set(rid)
        request.state.request_id = rid

        start = time.time()
        try:
            response: Response = await call_next(request)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(
                f"{request.method} {request.url.path} 异常 [{elapsed:.0f}ms]: {e}",
                exc_info=True,
            )
            raise
        elapsed = (time.time() - start) * 1000

        if response.status_code >= 400:
            logger.warning(f"{request.method} {request.url.path} -> {response.status_code} [{elapsed:.0f}ms]")
        else:
            logger.info(f"{request.method} {request.url.path} -> {response.status_code} [{elapsed:.0f}ms]")

        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", "-")
        logger.error(
            f"未处理异常 [{request.method} {request.url.path}]: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "request_id": rid},
        )

    return logger
