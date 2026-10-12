"""Single-pass hybrid RAG vs current routed Agentic RAG, using real providers.
Dry-run only validates cases. Live mode explicitly requires --live.
"""
import argparse
import asyncio
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from scripts.eval_quality import grade, read_cases, write_report

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals/answer_cases.jsonl"

async def evaluate_case(case, mode):
    from langchain_core.callbacks import BaseCallbackHandler
    from app.agents.answer_requirements import Clarification
    from app.agents.query_router import QueryRouter
    from app.agents.retrieval_tools import RETRIEVAL_TOOLS
    from app.services.llm_service import llm_service
    from app.services.rag_service import rag_service

    class Usage(BaseCallbackHandler):
        def __init__(self):
            self.calls = 0
            self.usage = []
        def on_chat_model_start(self, *args, **kwargs):
            self.calls += 1
        def on_llm_end(self, response, **kwargs):
            usage = (response.llm_output or {}).get("token_usage")
            if not usage:
                usage = getattr(response.generations[0][0].message, "usage_metadata", None)
            if usage:
                self.usage.append(dict(usage))

    tracker = Usage()
    old_model = llm_service._llm
    planner = llm_service.intent_with_tools(RETRIEVAL_TOOLS).with_config(callbacks=[tracker])
    checker = llm_service.coverage_checker().with_config(callbacks=[tracker])
    llm_service._llm = old_model.with_config(callbacks=[tracker])
    started = perf_counter()
    row = {"id": case["id"], "category": case["category"], "mode": mode}
    history = [SimpleNamespace(**item) for item in case.get("history", [])]
    try:
        if mode == "single":
            prepared = await rag_service.prepare(case["question"], history)
        else:
            prepared = await QueryRouter(planner, checker).prepare(case["question"], history)
        first = None
        parts = []
        sources = []
        if isinstance(prepared, Clarification):
            parts = [prepared.answer]
            first = (perf_counter()-started)*1000
        elif prepared is None:
            parts = ["根据目前的学校资料，我暂时无法回答这个问题。"]
            first = (perf_counter()-started)*1000
        else:
            messages, source_objects = prepared
            sources = [s.source for s in source_objects]
            async for token in llm_service.stream(messages):
                if first is None:
                    first = (perf_counter()-started)*1000
                parts.append(token)
        answer = "".join(parts)
        row.update(answer=answer, sources=sources, first_token_ms=first)
        row.update(grade(answer, sources, case))
    except Exception as error:
        row["error"] = type(error).__name__
    finally:
        llm_service._llm = old_model
    row.update(elapsed_ms=round((perf_counter()-started)*1000, 2),
               llm_calls=tracker.calls, token_usage=tracker.usage,
               token_usage_complete=len(tracker.usage) == tracker.calls,
               cost=None)
    return row

async def run(args, cases):
    # Fail before spending tokens if the configured local knowledge database is unavailable.
    from app.core.db import connect
    def probe():
        with connect() as connection:
            connection.execute("SELECT 1").fetchone()
    await asyncio.to_thread(probe)
    rows = []
    modes = ("single", "agentic") if args.mode == "both" else (args.mode,)
    for index, case in enumerate(cases):
        # Alternate order to reduce the influence of warming shared caches.
        ordered = modes if index % 2 == 0 else tuple(reversed(modes))
        for mode in ordered:
            rows.append(await evaluate_case(case, mode))
            write_report(args.output, rows, {"live": True, "baseline": "single hybrid document retrieval",
                "cost": "null: token prices not supplied; embedding/rerank cost excluded",
                "grading": "keyword facets and expected sources are proxies; human review required"})
            print(case["id"], mode, rows[-1].get("error", "completed"), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "evals/reports/answers.json")
    parser.add_argument("--mode", choices=("single", "agentic", "both"), default="both")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    cases = read_cases(args.cases)
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        cases = cases[:args.limit]
    if not args.live:
        print(f"Validated {len(cases)} answer cases; no API or database calls. Use --live to execute.")
        return
    try:
        asyncio.run(run(args, cases))
    finally:
        from app.core import db
        if db._pool is not None:
            db._pool.close()

if __name__ == "__main__":
    main()
