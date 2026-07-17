"""大模型调用客户端（流式重构版）

借鉴 SQLBot 的 provider-factory 模式，核心改进：
1. 流式输出 stream_chat() —— 逐 token yield，解决"回复太慢"
2. 线程安全 —— 每次请求从模型配置创建独立 AsyncOpenAI client，
   彻底避免全局单例 reconfigure() 的并发串台问题
3. 兼容 OpenAI API 格式
"""

from typing import Optional, List, Dict, AsyncIterator
from openai import AsyncOpenAI
import httpx
from config.settings import settings


class LLMClient:
    """统一大模型调用客户端（线程安全 + 流式）"""

    def __init__(self):
        # 全局默认配置（环境变量兜底）
        self._api_base: str = settings.LLM_API_BASE
        self._api_key: str = settings.LLM_API_KEY
        self._model: str = settings.LLM_DEFAULT_MODEL

    # ------------------------------------------------------------------
    #  client 工厂：每次调用创建独立 client，避免并发串台
    # ------------------------------------------------------------------
    def _create_client(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        stream: bool = False,
    ) -> AsyncOpenAI:
        """根据请求级配置创建独立 OpenAI 异步客户端

        Args:
            api_base / api_key: 请求级覆盖；不传则用全局默认
            stream: 流式请求时使用更宽松的 read timeout
        Returns:
            独立的 AsyncOpenAI 实例（不共享、用完即弃）
        """
        base_timeout = settings.LLM_TIMEOUT
        if stream:
            # 流式请求：连接超时30s，读取超时300s（允许模型思考停顿）
            timeout = httpx.Timeout(
                connect=30.0,
                read=float(base_timeout),
                write=30.0,
                pool=30.0,
            )
        else:
            timeout = httpx.Timeout(float(base_timeout))
        return AsyncOpenAI(
            base_url=api_base or self._api_base,
            api_key=api_key or self._api_key,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    #  非流式调用（向后兼容，降级回退用）
    # ------------------------------------------------------------------
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """非流式调用大模型对话

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大Token数
            api_base / api_key: 请求级覆盖配置
        Returns:
            AI响应文本（完整）
        """
        client = self._create_client(api_base, api_key)
        model_name = model or self._model
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        finally:
            await client.close()

    # ------------------------------------------------------------------
    #  流式调用（核心新增 —— 借鉴 SQLBot LLMService.stream 模式）
    # ------------------------------------------------------------------
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> AsyncIterator[Dict]:
        """流式调用大模型 —— 逐 token yield

        借鉴 SQLBot process_stream 的思路：从 OpenAI streaming response
        逐块提取 content，yield 标准化的 chunk 字典。

        Args:
            messages: 消息列表（含 system / user / assistant roles）
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大Token数
            api_base / api_key: 请求级覆盖配置
        Yields:
            {"type": "content", "content": "文本片段", "finish_reason": None/str}
        """
        client = self._create_client(api_base, api_key, stream=True)
        model_name = model or self._model
        try:
            stream = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                # 跳过空 choices（首帧可能只有 role）
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "content", "content": content, "finish_reason": None}

                if finish_reason:
                    yield {"type": "content", "content": "", "finish_reason": finish_reason}
        finally:
            await client.close()

    # ------------------------------------------------------------------
    #  向后兼容：保留 reconfigure（仅更新全局默认值，不再变异全局 client）
    # ------------------------------------------------------------------
    def reconfigure(self, api_base: str, api_key: str, model: str):
        """更新全局默认配置（不再重建全局 client，每次请求独立创建）"""
        self._api_base = api_base
        self._api_key = api_key
        self._model = model

    async def reconfigure_async(self, api_base: str, api_key: str, model: str):
        """异步版 reconfigure（保持向后兼容签名）"""
        self.reconfigure(api_base, api_key, model)


# 全局单例（仅持有默认配置，不再持有可变 client）
llm_client = LLMClient()
