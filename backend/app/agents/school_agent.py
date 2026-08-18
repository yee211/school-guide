from app.agents.query_router import QueryRouter
from app.services.llm_service import llm_service
from app.services.rag_service import RAGResult, SourceInfo
from app.structured.query import query_admission_data


class SchoolAgent:
    """薄编排器：路由准备消息 → 流式生成 → 包装 SSE 事件。

    路由与消息组装逻辑见 ``QueryRouter``；本类只负责把 router 产出的消息
    交给 ``llm_service`` 流式生成，并按 ``delta`` / ``done`` 事件格式输出。
    """

    def __init__(self, router: QueryRouter | None = None) -> None:
        self._router = router or QueryRouter(
            llm_tools=llm_service.intent_with_tools([query_admission_data]),
        )

    async def stream(self, message: str, history=None):
        """流式回答，逐段 yield ``{"type": "delta"|"done", ...}`` 事件。"""
        prepared = await self._router.prepare(message, history)

        if prepared is None:
            yield {
                "type": "delta",
                "content": "根据目前的学校资料，我暂时无法回答这个问题。",
            }
            yield {"type": "done", "sources": []}
            return

        gen_messages, sources = prepared
        async for token in llm_service.stream(gen_messages):
            yield {"type": "delta", "content": token}

        yield {
            "type": "done",
            "sources": [
                {"title": source.title, "source": source.source}
                for source in sources
            ],
        }

    async def chat(self, message: str, history=None) -> RAGResult:
        parts: list[str] = []
        sources: list[SourceInfo] = []

        async for event in self.stream(message, history):
            if event["type"] == "delta":
                parts.append(event["content"])
            elif event["type"] == "done":
                sources = [
                    SourceInfo(title=s["title"], source=s["source"])
                    for s in event["sources"]
                ]

        return RAGResult(answer="".join(parts), sources=sources)


school_agent = SchoolAgent()
