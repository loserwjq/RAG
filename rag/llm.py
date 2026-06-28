"""
LLM 调用模块 — 通过 OpenAI SDK 调用兼容 API。

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
from typing import Dict, Generator, List, Optional

from openai import OpenAI

from rag.config import LLMConfig


class LLMError(Exception):
    """LLM 调用异常。"""
    pass


class LLM:
    """OpenAI 兼容 API 客户端。"""

    def __init__(self, config: LLMConfig = None):
        self._config = config or LLMConfig()

        self._client = OpenAI(
            api_key=self._config.api_key,
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            max_retries=2,
            default_headers=self._config.extra_headers,
        )

    # ── 消息格式转换 ──────────────────────────────────────

    @staticmethod
    def _to_openai_messages(system: str, prompt: str = None, history: List[Dict] = None):
        """将系统提示词 + 用户输入 转为 OpenAI messages 格式。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            for m in history:
                messages.append({
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                })
        if prompt:
            messages.append({"role": "user", "content": prompt})
        return messages

    # ── 获取模型参数 ──────────────────────────────────────

    def _get_kwargs(self, temperature=None, max_tokens=None):
        kwargs = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        else:
            kwargs["temperature"] = self._config.temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = self._config.max_tokens
        return kwargs

    # ── 单次生成 ──────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str = None,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        system = system or self._config.system_prompt
        messages = self._to_openai_messages(system, prompt=prompt)
        kwargs = self._get_kwargs(temperature, max_tokens)

        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=messages,
                **kwargs,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise LLMError(f"LLM 生成失败: {e}")

    # ── 多轮对话 ──────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict[str, str]],
        system: str = None,
        temperature: float = None,
    ) -> str:
        system = system or self._config.system_prompt
        openai_messages = self._to_openai_messages(system, history=messages)
        kwargs = self._get_kwargs(temperature)

        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=openai_messages,
                **kwargs,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise LLMError(f"LLM 多轮对话失败: {e}")

    # ── 流式生成 ──────────────────────────────────────────

    def stream(
        self,
        prompt: str,
        system: str = None,
        temperature: float = None,
        max_tokens: int = None,
    ) -> Generator[str, None, None]:
        system = system or self._config.system_prompt
        messages = self._to_openai_messages(system, prompt=prompt)
        kwargs = self._get_kwargs(temperature, max_tokens)

        try:
            stream = self._client.chat.completions.create(
                model=self._config.model,
                messages=messages,
                stream=True,
                **kwargs,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise LLMError(f"流式生成失败: {e}")

    # ── RAG 专用：基于上下文回答 ──────────────────────────

    def answer_with_context(
        self,
        question: str,
        context: str,
        system: str = None,
    ) -> str:
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

    # ── Query Rewriting ────────────────────────────────────

    def rewrite_query(self, query: str) -> str:
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

    # ── 健康检查 ──────────────────────────────────────────

    def check_health(self) -> Dict[str, any]:
        try:
            models_resp = self._client.models.list()
            models = [m.id for m in models_resp.data]
            return {
                "status": "ok",
                "models": models[:10],
                "target_model": self._config.model,
                "model_available": self._config.model in models,
            }
        except Exception:
            try:
                self.generate("hi", max_tokens=5)
                return {
                    "status": "ok",
                    "models": [self._config.model],
                    "target_model": self._config.model,
                    "model_available": True,
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "hint": f"请检查 API Key 和网络连接 ({self._config.base_url})",
                }

    @property
    def model(self) -> str:
        return self._config.model
