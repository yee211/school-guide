"""Shared retrieval tool contracts and evidence; never execute model-generated SQL."""
import asyncio
from dataclasses import dataclass, field
from hashlib import sha256

from langchain_core.tools import tool

from app.rag.indexer import build_chunk_id
from app.rag.retriever import retriever_service
from app.services.rag_service import SourceInfo
from app.structured.query import StructuredResult, structured_query_service


@dataclass(frozen=True)
class Evidence:
    key: str
    content: str
    sources: tuple[SourceInfo, ...]
    facts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    evidence: tuple[Evidence, ...] = ()
    note: str = ""


async def execute_retrieval(name: str, query: str) -> ToolResult:
    if name == "search_school_knowledge":
        documents = await retriever_service.search(query=query, top_k=5)
        evidence = []
        for doc in documents:
            source = str(doc.metadata.get("source", "未知来源"))
            title = str(doc.metadata.get("title", "未知资料"))
            years = doc.metadata.get("years", [])
            content = f"文档检索；标题：{title}；年份：{years}；来源：{source}\n{doc.page_content}"
            evidence.append(Evidence(build_chunk_id(doc), content, (SourceInfo(title, source),)))
        return ToolResult(tuple(evidence), "" if evidence else "文档检索未找到结果。")
    if name == "query_admission_data":
        result = await asyncio.to_thread(structured_query_service.query_and_format, query)
        # One complete row per evidence entry: budgeting never cuts a numeric row in half.
        evidence = []
        for attr in ("score_rows", "plan_rows"):
            for row in getattr(result, attr):
                source = str(row.get("source_file") or "未知来源")
                subset = StructuredResult(**{attr: [row]}, source_files=(source,))
                content = "结构化精确查询\n" + subset.format_context()
                key = "structured:" + sha256(content.encode()).hexdigest()
                title = source.rsplit("/", 1)[-1].removesuffix(".md")
                evidence.append(Evidence(key, content, (SourceInfo(title, source),), dict(row)))
        return ToolResult(tuple(evidence), result.guidance or ("" if evidence else result.format_context()))
    raise ValueError("Unknown retrieval tool")


@tool
async def search_school_knowledge(query: str) -> str:
    """检索长沙工业学院的专业特色、就业方向、校园设施、政策等文档。query 必须是完整查询。"""
    result = await execute_retrieval("search_school_knowledge", query)
    return "\n\n".join(item.content for item in result.evidence) or result.note


@tool
async def query_admission_data(question: str) -> str:
    """查询长沙工业学院的分数线、位次、招生人数、学费。question 须含已知年份、省份、科类、专业；不改变指定年份。"""
    result = await execute_retrieval("query_admission_data", question)
    return "\n\n".join(item.content for item in result.evidence) or result.note


RETRIEVAL_TOOLS = [query_admission_data, search_school_knowledge]
