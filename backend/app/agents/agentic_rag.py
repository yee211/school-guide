"""Bounded retrieval agent. Planner output is never used as answer evidence."""
import asyncio
import logging
import json
from dataclasses import dataclass, field
from time import monotonic

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.agents.answer_requirements import build_requirements, validate_coverage
from app.agents.retrieval_tools import Evidence, execute_retrieval
from app.core.exceptions import LLMConnectionError
from app.core.config import (
    AGENT_MAX_ROUNDS, AGENT_MAX_TOOL_CALLS, AGENT_TIMEOUT_SECONDS,
    AGENT_STEP_TIMEOUT_SECONDS, AGENT_CONTEXT_CHARS,
)
from app.prompts.agentic_prompt import AGENTIC_ANSWER_PROMPT, AGENTIC_RETRIEVAL_PROMPT, COVERAGE_CHECK_PROMPT
from app.prompts.rag_prompt import RAG_INPUT_TEMPLATE
from app.prompts.school_prompt import SCHOOL_SYSTEM_PROMPT
from app.services.rag_service import RAGService

logger = logging.getLogger("uvicorn.error.agentic_rag")


@dataclass
class RetrievalState:
    evidence: dict[str, Evidence] = field(default_factory=dict)
    cache: dict[tuple[str, str], str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    chars: int = 0
    calls: int = 0
    rounds: int = 0
    coverage: dict[str, str] = field(default_factory=dict)
    failures: int = 0
    successes: int = 0

    def add(self, result):
        admitted = []
        for item in result.evidence:
            if item.key in self.evidence:
                admitted.append(f"已有证据：{item.key}（未新增内容）")
                continue
            if self.chars + len(item.content) > AGENT_CONTEXT_CHARS:
                if "证据达到长度上限，部分结果未纳入。" not in self.notes:
                    self.notes.append("证据达到长度上限，部分结果未纳入。")
                continue
            self.evidence[item.key] = item
            self.chars += len(item.content)
            admitted.append(item.content)
        if result.note:
            self.notes.append(result.note[:500])
        text = "\n\n".join(admitted) or result.note or "结果未纳入证据预算，请缩小查询。"
        if len(text) > 6000:
            text = text[:6000] + "\n[规划器预览已截断，最终证据保留在请求状态中；请缩小查询核对缺失项。]"
        return text


class AgenticRAG:
    def __init__(self, planner, executor=None, coverage_checker=None, *, catalog_loader=None):
        self.catalog_loader = catalog_loader
        self.planner = planner
        self.coverage_checker = coverage_checker
        self.executor = executor or execute_retrieval

    async def prepare(self, question, history=None, *, search_query=None):
        state = RetrievalState()
        query = search_query or question
        started = monotonic()
        deadline = started + AGENT_TIMEOUT_SECONDS
        catalog = None
        catalog_unavailable = False
        if self.catalog_loader is not None:
            try:
                catalog = await asyncio.wait_for(
                    asyncio.to_thread(self.catalog_loader),
                    timeout=max(0, min(2.0, deadline - monotonic())),
                )
            except Exception:
                logger.warning("Requirement catalog unavailable; retaining original query")
                catalog_unavailable = True
        requirements = (build_requirements(query, catalog, catalog_unavailable=catalog_unavailable)
                        if self.catalog_loader is not None else build_requirements(query))
        checklist = "\n".join(f"{r.id}: {r.label}" for r in requirements)
        messages = [
            SystemMessage(content=AGENTIC_RETRIEVAL_PROMPT),
            *RAGService._history_to_messages(history),
            HumanMessage(content=f"原问题：{question}\n补全问题：{query}\n逐项需求清单：\n{checklist}"),
        ]

        async def bounded(awaitable):
            remaining = deadline - monotonic()
            return await asyncio.wait_for(awaitable, timeout=max(0, min(remaining, AGENT_STEP_TIMEOUT_SECONDS)))

        async def execute(name, args):
            parameter = "question" if name == "query_admission_data" else "query"
            value = args.get(parameter) if isinstance(args, dict) else None
            if name not in ("query_admission_data", "search_school_knowledge"):
                return "未知工具，仅允许结构化查询或文档检索。"
            if not isinstance(value, str) or not value.strip() or len(value) > 5000:
                return "查询参数无效，请提供不超过5000字符的完整问题。"
            value = " ".join(value.split())
            key = (name, value)
            if key in state.cache:
                return "重复查询，复用此前结果；请检查已返回的证据、换查询或停止。"
            state.calls += 1
            try:
                result = await bounded(self.executor(name, value))
                state.successes += 1
                text = state.add(result)
                state.coverage.clear()
            except TimeoutError:
                raise
            except Exception:
                state.failures += 1
                logger.warning("Retrieval tool failed: %s", name, exc_info=True)
                text = "工具执行失败，不能据此推断学校事实。"
                state.notes.append(text)
            state.cache[key] = text
            return text

        async def fallback_retrieval():
            # Preserve requirement-specific tools and conditions when planning fails.
            candidates = [(r.tool, r.query) for r in requirements]
            if not candidates:
                candidates = [("search_school_knowledge", query)]
            seen = set(state.cache)
            pending = []
            for name, value in candidates:
                value = " ".join(value.split())
                key = (name, value)
                if key not in seen:
                    seen.add(key)
                    pending.append(key)
            pending = pending[:max(0, AGENT_MAX_TOOL_CALLS - state.calls)]
            if monotonic() >= deadline:
                return
            results = await asyncio.gather(*[
                execute(name, {"question" if name == "query_admission_data" else "query": value})
                for name, value in pending
            ], return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result

        async def assess():
            if not self.coverage_checker or len(requirements) < 2:
                return []
            if state.coverage:
                return [r for r in requirements if state.coverage.get(r.id) == "missing"]
            if not state.evidence:
                state.coverage = {r.id: "missing" for r in requirements}
                return requirements
            evidence_text = "\n\n".join(f"证据ID：{key}\n{item.content}" for key, item in state.evidence.items())
            report = await bounded(self.coverage_checker.ainvoke([
                SystemMessage(content=COVERAGE_CHECK_PROMPT),
                HumanMessage(content=f"问题：{question}\n需求：\n{checklist}\n证据：\n{evidence_text}"),
            ]))
            state.coverage = validate_coverage(requirements, state.evidence, report)
            return [r for r in requirements if state.coverage.get(r.id) == "missing"]

        try:
            for _ in range(AGENT_MAX_ROUNDS):
                state.rounds += 1
                try:
                    response = await bounded(self.planner.ainvoke(messages))
                except TimeoutError:
                    raise
                except Exception:
                    logger.warning("Retrieval planner failed", exc_info=True)
                    state.notes.append("检索规划失败，使用已取得证据。")
                    if not state.evidence and not state.cache and state.calls < AGENT_MAX_TOOL_CALLS:
                        await fallback_retrieval()
                    break
                # Do not retain free-form planner text or unbounded batches.
                response = response.model_copy(update={
                    "content": "",
                    "tool_calls": response.tool_calls[:AGENT_MAX_TOOL_CALLS - state.calls],
                })
                calls = response.tool_calls
                if not calls:
                    # Never accept an ungrounded school answer from the planner.
                    if not state.evidence and not state.cache and state.calls < AGENT_MAX_TOOL_CALLS:
                        await fallback_retrieval()
                        messages.append(HumanMessage(content="已执行默认检索：\n" + "\n".join(state.cache.values())))
                        continue
                    if self.coverage_checker and len(requirements) > 1:
                        try:
                            missing = await assess()
                        except TimeoutError:
                            raise
                        except Exception:
                            logger.warning("Coverage assessment failed", exc_info=True)
                            state.notes.append("逐项覆盖检查失败，不能确认所有需求已覆盖。")
                            break
                        pending = [r for r in missing if (r.tool, " ".join(r.query.split())) not in state.cache]
                        pending = pending[:AGENT_MAX_TOOL_CALLS - state.calls]
                        if pending:
                            # Independent missing items share the same deadline and call budget.
                            texts = await asyncio.gather(*[
                                execute(r.tool, {"question" if r.field else "query": r.query}) for r in pending
                            ], return_exceptions=True)
                            if any(isinstance(text, TimeoutError) for text in texts):
                                raise TimeoutError
                            texts = [str(text) for text in texts]
                            messages.append(HumanMessage(content="逐项检查发现缺失，已定向补查：\n" + "\n\n".join(texts)))
                            if state.calls < AGENT_MAX_TOOL_CALLS:
                                continue
                    break
                messages.append(response)
                for call in calls:
                    if state.calls >= AGENT_MAX_TOOL_CALLS:
                        text = "工具调用预算已耗尽，停止检索。"
                    else:
                        text = await execute(call["name"], call.get("args", {}))
                    messages.append(ToolMessage(content=text, tool_call_id=call["id"]))
                if state.calls >= AGENT_MAX_TOOL_CALLS or state.chars >= AGENT_CONTEXT_CHARS:
                    state.notes.append("检索达到预算上限，可能仍有未覆盖的问题。")
                    break
            else:
                state.notes.append("检索达到轮次上限，可能仍有未覆盖的问题。")
        except TimeoutError:
            # A timed-out planning step may leave budget for requirement-specific retrieval.
            if not state.evidence and not state.cache and state.calls < AGENT_MAX_TOOL_CALLS and monotonic() < deadline:
                try:
                    await fallback_retrieval()
                except TimeoutError:
                    pass
            state.notes.append("检索达到时间上限，可能仍有未覆盖的问题。")
        if self.coverage_checker and len(requirements) > 1 and not state.coverage and monotonic() < deadline:
            try:
                missing = await assess()
                pending = [r for r in missing if (r.tool, " ".join(r.query.split())) not in state.cache]
                pending = pending[:AGENT_MAX_TOOL_CALLS - state.calls]
                if pending and monotonic() < deadline:
                    results = await asyncio.gather(*[
                        execute(r.tool, {"question" if r.field else "query": r.query}) for r in pending
                    ], return_exceptions=True)
                    if any(isinstance(result, Exception) for result in results):
                        state.notes.append("部分定向补查超时或失败。")
                    if not state.coverage and monotonic() < deadline:
                        await assess()
            except Exception:
                state.notes.append("未能完成最终逐项覆盖检查，缺失项应如实说明。")
        if requirements:
            state.notes.append("需求检查清单：" + "；".join(
                f"{r.label}：" + {"supported": "有证据", "missing": "未找到匹配证据", "conflict": "证据存在冲突"}.get(state.coverage.get(r.id), "未核验，请依据原文检查")
                for r in requirements
            ))
        logger.info("Agent retrieval rounds=%d calls=%d evidence=%d coverage=%s elapsed_ms=%.0f", state.rounds, state.calls, len(state.evidence), state.coverage, (monotonic() - started) * 1000)
        if state.failures and not state.successes and not state.evidence:
            raise LLMConnectionError("知识库检索服务暂时不可用")
        if not state.evidence and not state.cache:
            return None
        sources = {}
        parts = []
        for index, item in enumerate(state.evidence.values(), 1):
            parts.append(f"[资料 {index}]\n{item.content}")
            for source in item.sources:
                sources.setdefault(source.source, source)
        context = "\n\n".join(parts) or "本轮检索未取得可用事实证据。"
        notes = "\n".join(dict.fromkeys(state.notes))[:2000]
        # Fresh answer messages exclude planner responses and raw tool protocol.
        final = [
            SystemMessage(content=SCHOOL_SYSTEM_PROMPT + AGENTIC_ANSWER_PROMPT),
            *RAGService._history_to_messages(history),
            HumanMessage(content=RAG_INPUT_TEMPLATE.format(context=context, question=question) + f"\n补全问题：{query}\n执行备注（不是事实证据）：{notes}"),
        ]
        return final, list(sources.values())
