import json
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from app.agents.school_agent import school_agent
from app.core.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMTimeoutError,
)

router = APIRouter(prefix="/chat", tags=["chat"])


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=5000)

class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=5000)
    history: list[HistoryMessage] = Field(default_factory=list)

class SourceResponse(BaseModel):
    title: str
    source: str

class ChatResponse(BaseModel):
    message: str
    answer: str
    sources: list[SourceResponse]

@router.post("",response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await school_agent.chat(request.message, request.history)
        return ChatResponse(
            message=request.message,
            answer=result.answer,
            sources=[
                SourceResponse(
                    title=source.title,
                    source=source.source,
                )
                for source in result.sources
            ]
        )

    except LLMAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "llm_authentication_failed",
                "message": "模型服务配置异常，请联系管理员",
            },
        ) from exc

    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "code": "llm_timeout",
                "message": "模型响应超时，请稍后重试",
            },
        ) from exc

    except LLMConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "llm_connection_failed",
                "message": "暂时无法连接模型服务，请稍后重试",
            },
        ) from exc

    except LLMEmptyResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "llm_empty_response",
                "message": "模型没有返回有效内容，请重新提问",
            },
        ) from exc

    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "llm_provider_error",
                "message": "模型服务暂时异常，请稍后重试",
            },
        ) from exc


def _sse_error(message: str) -> str:
    return f"data: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式回答：逐段 delta，结尾 done 带 sources，出错发 error。"""

    async def event_stream():
        try:
            async for event in school_agent.stream(request.message, request.history):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except LLMAuthenticationError:
            yield _sse_error("模型服务配置异常，请联系管理员")
        except LLMTimeoutError:
            yield _sse_error("模型响应超时，请稍后重试")
        except LLMConnectionError:
            yield _sse_error("暂时无法连接模型服务，请稍后重试")
        except LLMEmptyResponseError:
            yield _sse_error("模型没有返回有效内容，请重新提问")
        except LLMProviderError:
            yield _sse_error("模型服务暂时异常，请稍后重试")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
