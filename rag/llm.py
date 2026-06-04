"""
LLM 调用模块 — 通过 OpenAI 兼容 API 调用 Qwen3 模型。

支持:
    - Gitee AI (默认)
    - 任何 OpenAI 兼容 API（DashScope、Ollama 等）
    - 流式输出
    - 自动重试

用法:
    from rag.llm import LLM
    llm = LLM()
    answer = llm.generate("你好")
    # 流式
    for chunk in llm.stream("你好"):
        print(chunk, end="")
"""

import json
import time
from typing import Dict, Generator, List, Optional

from rag.config import LLMConfig


class LLMError(Exception):
    """LLM 调用异常。"""
    pass


class LLM:
    """OpenAI 兼容 API 客户端（支持 Gitee AI / DashScope / Ollama）。"""

    def __init__(self, config: LLMConfig = None):
        self._config = config or LLMConfig()

    # ── 单次生成 ──────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str = None,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """
        调用 LLM 生成完整回答。

        参数:
            prompt: 用户输入
            system: 系统提示词（默认用配置值）
            temperature: 生成温度
            max_tokens: 最大 token 数

        返回: 生成的文本
        """
        system = system or self._config.system_prompt
        temperature = temperature if temperature is not None else self._config.temperature
        max_tokens = max_tokens or self._config.max_tokens

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        payload = {
            "model": self._config.model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.7,
            "top_k": 50,
            "frequency_penalty": 1,
        }

        url = f"{self._config.base_url}/chat/completions"
        return self._request(url, payload)

    # ── 多轮对话 ──────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict[str, str]],
        system: str = None,
        temperature: float = None,
    ) -> str:
        """
        多轮对话。

        参数:
            messages: [{"role": "user"/"assistant", "content": "..."}]
            system: 系统提示词

        返回: 助手回复
        """
        system = system or self._config.system_prompt
        temperature = temperature if temperature is not None else self._config.temperature

        full_messages = [{"role": "system", "content": system}] + messages

        payload = {
            "model": self._config.model,
            "messages": full_messages,
            "stream": False,
            "max_tokens": self._config.max_tokens,
            "temperature": temperature,
            "top_p": 0.7,
            "top_k": 50,
            "frequency_penalty": 1,
        }

        url = f"{self._config.base_url}/chat/completions"
        return self._request(url, payload)

    # ── 流式生成 ──────────────────────────────────────────

    def stream(
        self,
        prompt: str,
        system: str = None,
        temperature: float = None,
    ) -> Generator[str, None, None]:
        """
        流式生成，逐 token 返回。

        用法:
            for chunk in llm.stream("你好"):
                print(chunk, end="", flush=True)
        """
        import urllib.request

        system = system or self._config.system_prompt
        temperature = temperature if temperature is not None else self._config.temperature

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        payload = {
            "model": self._config.model,
            "messages": messages,
            "stream": True,
            "max_tokens": self._config.max_tokens,
            "temperature": temperature,
            "top_p": 0.7,
            "top_k": 50,
            "frequency_penalty": 1,
        }

        url = f"{self._config.base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }
        if self._config.extra_headers:
            headers.update(self._config.extra_headers)

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                for line in resp:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        # 正文内容
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            raise LLMError(f"流式生成失败: {e}")

    # ── RAG 专用：基于上下文回答 ──────────────────────────

    def answer_with_context(
        self,
        question: str,
        context: str,
        system: str = None,
    ) -> str:
        """
        基于检索上下文回答问题（RAG 核心调用）。

        参数:
            question: 用户问题
            context: 检索到的参考文档（已拼接）
            system: 系统提示词

        返回: LLM 生成的答案
        """
        prompt = f"""请基于以下参考文档回答用户的问题。

要求：
1. 只使用参考文档中的信息来回答
2. 如果文档中没有相关信息，明确说明"根据现有资料无法回答该问题"
3. 回答要简洁准确，必要时分点列出
4. 如果涉及具体数字、日期、流程，请准确引用
5. 回答中引用来源时使用文档的实际名称，不要用"文档1""文档9"等编号

参考文档：
{context}

用户问题：{question}"""

        return self.generate(prompt, system=system)

    def stream_with_context(
        self,
        question: str,
        context: str,
        system: str = None,
    ) -> Generator[str, None, None]:
        """基于上下文流式回答。"""
        prompt = f"""请基于以下参考文档回答用户的问题。

要求：
1. 只使用参考文档中的信息来回答
2. 如果文档中没有相关信息，明确说明"根据现有资料无法回答该问题"
3. 回答要简洁准确，必要时分点列出
4. 如果涉及具体数字、日期、流程，请准确引用
5. 回答中引用来源时使用文档的实际名称，不要用"文档1""文档9"等编号

参考文档：
{context}

用户问题：{question}"""

        yield from self.stream(prompt, system=system)

    # ── 内部方法 ──────────────────────────────────────────

    def _request(self, url: str, payload: dict, retries: int = 2) -> str:
        """发送请求到 API，带重试。"""
        import urllib.request
        import urllib.error

        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }
        if self._config.extra_headers:
            headers.update(self._config.extra_headers)

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        last_error = None
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    # OpenAI 格式响应
                    choices = result.get("choices", [])
                    if choices:
                        return choices[0]["message"]["content"]
                    raise LLMError(f"API 返回无 choices: {result}")
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                last_error = f"HTTP {e.code}: {body[:200]}"
                if e.code == 429:  # Rate limit
                    time.sleep(2 * (attempt + 1))
                    continue
                elif e.code >= 500:
                    time.sleep(1)
                    continue
                else:
                    break
            except urllib.error.URLError as e:
                last_error = str(e)
                if attempt < retries:
                    time.sleep(1)
                    continue
            except (KeyError, json.JSONDecodeError) as e:
                raise LLMError(f"API 响应解析失败: {e}")

        raise LLMError(
            f"无法连接 LLM API ({self._config.base_url})。\n"
            f"错误: {last_error}"
        )

    # ── Query Rewriting ────────────────────────────────────

    def rewrite_query(self, query: str) -> str:
        """
        检索前问题改写：修正拼写错误 + 展开缩写 + 优化检索效果。

        用于提升对带拼写错误、简称、中英混合等查询的召回率。

        参数:
            query: 原始用户输入

        返回: 改写后的查询文本（失败时返回原始 query）

        用法:
            rewritten = llm.rewrite_query("Tonala是什么")
            # → "Tonale是什么？Alfa Romeo Tonale车型介绍"
        """
        if not self._config.rewrite_enabled:
            return query

        try:
            result = self.generate(
                prompt=query,
                system=self._config.rewrite_prompt,
                temperature=self._config.rewrite_temperature,
                max_tokens=self._config.rewrite_max_tokens,
            )
            rewritten = result.strip().strip('"').strip("'").strip()
            # 如果 LLM 返回空或明显异常（太长），退回原始 query
            if not rewritten or len(rewritten) > len(query) * 5:
                return query
            return rewritten
        except LLMError as e:
            print(f"[LLM] Query rewriting failed, using original: {e}")
            return query

    # ── 对话摘要 ──────────────────────────────────────────

    def summarize_conversation(
        self,
        messages: List[Dict[str, str]],
        existing_summary: str = "",
    ) -> str:
        """
        将早期对话压缩为一段摘要，用于 LLM 上下文管理。

        参数:
            messages: [{"role": "user"/"assistant", "content": "..."}]
            existing_summary: 已有的摘要（追加场景时合并）

        返回: 摘要文本
        """
        if not messages:
            return existing_summary or ""

        history_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
            for m in messages
        )

        merge_hint = ""
        if existing_summary:
            merge_hint = f"\n之前的对话摘要：\n{existing_summary}\n请将新内容合并到已有摘要中。"

        prompt = f"""请用一段话（不超过200字）总结以下对话的关键信息。只输出摘要，不要任何格式或解释。

{merge_hint}

对话内容：
{history_text}
"""

        try:
            result = self.generate(
                prompt=prompt,
                system="你是一个对话摘要工具，用简洁的语言总结用户与助手的对话要点。",
                temperature=0.1,
                max_tokens=256,
            )
            return result.strip()
        except LLMError as e:
            print(f"[LLM] 摘要生成失败: {e}")
            return existing_summary or history_text[:500]

    # ── 工具 ──────────────────────────────────────────────

    def check_health(self) -> Dict[str, any]:
        """检查 API 服务状态。"""
        import urllib.request
        import urllib.error

        try:
            # 尝试列出模型
            url = f"{self._config.base_url}/models"
            headers = {
                "Authorization": f"Bearer {self._config.api_key}",
            }
            if self._config.extra_headers:
                headers.update(self._config.extra_headers)

            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("id", m.get("name", "")) for m in data.get("data", [])]
                return {
                    "status": "ok",
                    "models": models[:10],  # 只显示前10个
                    "target_model": self._config.model,
                    "model_available": any(
                        self._config.model in m for m in models
                    ),
                }
        except Exception as e:
            # 即使 /models 不可用，API 可能仍然可用
            # 尝试简单请求
            try:
                test_payload = {
                    "model": self._config.model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                    "stream": False,
                }
                url = f"{self._config.base_url}/chat/completions"
                data = json.dumps(test_payload).encode("utf-8")
                headers2 = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._config.api_key}",
                }
                if self._config.extra_headers:
                    headers2.update(self._config.extra_headers)
                req2 = urllib.request.Request(url, data=data, headers=headers2, method="POST")
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    json.loads(resp2.read().decode("utf-8"))
                    return {
                        "status": "ok",
                        "models": [self._config.model],
                        "target_model": self._config.model,
                        "model_available": True,
                    }
            except Exception as e2:
                return {
                    "status": "error",
                    "error": str(e2),
                    "hint": f"请检查 API Key 和网络连接 ({self._config.base_url})",
                }

    @property
    def model(self) -> str:
        return self._config.model
