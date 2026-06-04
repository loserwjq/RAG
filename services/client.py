"""
服务间 HTTP 调用客户端。

功能：
- 自动传递 X-Request-ID
- 超时 + 重试
- 错误时记录目标服务和请求参数
"""

import httpx
import logging
from typing import Any, Optional

from services.logger import request_id_var

DEFAULT_TIMEOUT = 120.0
MAX_RETRIES = 2

SERVICE_URLS = {
    "doc": "http://localhost:8001",
    "vector": "http://localhost:8002",
    "reranker": "http://localhost:8003",
    "llm": "http://localhost:8004",
}


class ServiceClient:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self._client

    def _headers(self) -> dict:
        return {"X-Request-ID": request_id_var.get("-")}

    async def call(
        self,
        service: str,
        path: str,
        method: str = "POST",
        json: Any = None,
        timeout: Optional[float] = None,
        retries: int = MAX_RETRIES,
    ) -> dict:
        url = f"{SERVICE_URLS[service]}{path}"
        client = await self._get_client()
        last_err = None

        for attempt in range(retries + 1):
            try:
                resp = await client.request(
                    method,
                    url,
                    json=json,
                    headers=self._headers(),
                    timeout=timeout or DEFAULT_TIMEOUT,
                )
                if resp.status_code >= 500 and attempt < retries:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    self.logger.warning(f"[{service}] {path} 重试 {attempt+1}/{retries}: {last_err}")
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException as e:
                last_err = f"超时: {e}"
                self.logger.warning(f"[{service}] {path} 超时, 重试 {attempt+1}/{retries}")
            except httpx.HTTPStatusError as e:
                last_err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                if e.response.status_code < 500:
                    self.logger.error(f"[{service}] {path} 客户端错误: {last_err}")
                    raise
                self.logger.warning(f"[{service}] {path} 服务端错误, 重试 {attempt+1}/{retries}")
            except httpx.ConnectError as e:
                last_err = f"连接失败: {e}"
                self.logger.error(f"[{service}] {path} 连接失败: {e}")
                if attempt < retries:
                    continue
                raise

        self.logger.error(f"[{service}] {path} 最终失败: {last_err}")
        raise RuntimeError(f"服务 {service} 调用失败: {last_err}")

    async def stream(self, service: str, path: str, json: Any = None):
        url = f"{SERVICE_URLS[service]}{path}"
        client = await self._get_client()
        try:
            async with client.stream(
                "POST", url, json=json, headers=self._headers(), timeout=DEFAULT_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        yield line
        except Exception as e:
            self.logger.error(f"[{service}] {path} 流式调用失败: {e}")
            raise

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
