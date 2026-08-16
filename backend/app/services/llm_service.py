import logging
import openai
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from app.core.config import (
    INTENT_LLM_MODEL_ID,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL_ID,
)
from app.core.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self) -> None:
      self._llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL_ID,
        timeout=30.0,
        max_retries=1
      )
      self._intent_llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=INTENT_LLM_MODEL_ID,
        timeout=30.0,
        max_retries=1
      )

    def with_tools(self, tools: list) -> "ChatOpenAI":
      """返回绑定工具（function calling）的 LLM，供 agent 做意图识别。"""
      return self._llm.bind_tools(tools)

    def intent_with_tools(self, tools: list) -> "ChatOpenAI":
      """意图识别专用（可用更快的模型档位），返回绑定工具的 LLM。"""
      return self._intent_llm.bind_tools(tools)

    async def invoke(self, messages: list[BaseMessage]) -> str:
        try:
            response = await self._llm.ainvoke(messages)

        except openai.AuthenticationError as exc:
            logger.error("LLM authentication failed")
            raise LLMAuthenticationError("模型服务鉴权失败") from exc

        except openai.APITimeoutError as exc:
            logger.warning("LLM request timed out")
            raise LLMTimeoutError("模型响应超时") from exc

        except openai.APIConnectionError as exc:
            logger.warning("Unable to connect to LLM provider")
            raise LLMConnectionError("无法连接模型服务") from exc

        except openai.APIError as exc:
            logger.exception("LLM provider returned an error")
            raise LLMProviderError("模型服务调用失败") from exc

        content = response.content

        if not isinstance(content, str) or not content.strip():
            logger.warning("LLM returned empty content")
            raise LLMEmptyResponseError("模型没有返回有效内容")

        return content.strip()

    async def stream(self, messages: list[BaseMessage]):
        """流式生成回答，逐段 yield 文本内容。"""
        try:
            async for chunk in self._llm.astream(messages):
                content = chunk.content
                if isinstance(content, str) and content:
                    yield content

        except openai.AuthenticationError as exc:
            logger.error("LLM authentication failed")
            raise LLMAuthenticationError("模型服务鉴权失败") from exc

        except openai.APITimeoutError as exc:
            logger.warning("LLM request timed out")
            raise LLMTimeoutError("模型响应超时") from exc

        except openai.APIConnectionError as exc:
            logger.warning("Unable to connect to LLM provider")
            raise LLMConnectionError("无法连接模型服务") from exc

        except openai.APIError as exc:
            logger.exception("LLM provider returned an error")
            raise LLMProviderError("模型服务调用失败") from exc

llm_service = LLMService()
