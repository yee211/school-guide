import argparse
import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from langchain_core.documents import Document

from app.rag.indexer import build_chunk_id
from app.rag.postgres_store import postgres_knowledge_store
from app.rag.retriever import retriever_service


DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "retrieval_cases.jsonl"
)


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    query: str
    relevant_sources: tuple[str, ...]
    must_contain: tuple[str, ...]


def load_cases(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        try:
            cases.append(
                EvaluationCase(
                    case_id=raw["id"],
                    query=raw["query"],
                    relevant_sources=tuple(
                        raw.get("relevant_sources", [])
                    ),
                    must_contain=tuple(raw.get("must_contain", [])),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"Missing {exc.args[0]!r} in {path}:{line_number}"
            ) from exc

    if not cases:
        raise ValueError(f"No evaluation cases found in {path}")
    return cases


def is_relevant(document: Document, case: EvaluationCase) -> bool:
    source = str(document.metadata.get("source", "")).replace("\\", "/")
    source_matches = (
        not case.relevant_sources
        or any(
            source.endswith(f"/{expected}") or source == expected
            for expected in case.relevant_sources
        )
    )
    content_matches = all(
        phrase in document.page_content
        for phrase in case.must_contain
    )
    return source_matches and content_matches


def document_ids(documents: list[Document]) -> list[str]:
    return [build_chunk_id(document) for document in documents]


def recall_at_k(
    ranked_documents: list[Document],
    relevant_ids: set[str],
    k: int,
) -> float:
    retrieved = set(document_ids(ranked_documents[:k]))
    return len(retrieved & relevant_ids) / len(relevant_ids)


def reciprocal_rank(
    ranked_documents: list[Document],
    relevant_ids: set[str],
    k: int,
) -> float:
    for rank, document_id in enumerate(
        document_ids(ranked_documents[:k]),
        start=1,
    ):
        if document_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    ranked_documents: list[Document],
    relevant_ids: set[str],
    k: int,
) -> float:
    gains = [
        1.0 if document_id in relevant_ids else 0.0
        for document_id in document_ids(ranked_documents[:k])
    ]
    dcg = sum(
        gain / math.log2(rank + 1)
        for rank, gain in enumerate(gains, start=1)
    )
    ideal_relevant_count = min(len(relevant_ids), k)
    ideal_dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(1, ideal_relevant_count + 1)
    )
    return dcg / ideal_dcg if ideal_dcg else 0.0


async def evaluate(
    cases: list[EvaluationCase],
    candidate_count: int,
    top_k: int,
) -> dict:
    corpus = await asyncio.to_thread(
        postgres_knowledge_store.list_documents
    )
    if not corpus:
        raise RuntimeError("The PostgreSQL knowledge index is empty")

    results: list[dict] = []
    for case in cases:
        relevant_ids = {
            build_chunk_id(document)
            for document in corpus
            if is_relevant(document, case)
        }
        if not relevant_ids:
            raise ValueError(
                f"Case {case.case_id!r} has no relevant chunks in the corpus"
            )

        trace = await retriever_service.search_with_trace(
            query=case.query,
            top_k=top_k,
            candidate_count=candidate_count,
        )
        semantic_documents = [
            document for document, _ in trace.semantic_results
        ]
        lexical_documents = [
            document for document, _ in trace.lexical_results
        ]
        final_hit = any(
            document_id in relevant_ids
            for document_id in document_ids(trace.documents)
        )
        results.append(
            {
                "id": case.case_id,
                "semantic_recall": recall_at_k(
                    semantic_documents,
                    relevant_ids,
                    candidate_count,
                ),
                "bm25_recall": recall_at_k(
                    lexical_documents,
                    relevant_ids,
                    candidate_count,
                ),
                "hybrid_recall": recall_at_k(
                    trace.fused_candidates,
                    relevant_ids,
                    candidate_count,
                ),
                "mrr": reciprocal_rank(
                    trace.documents,
                    relevant_ids,
                    top_k,
                ),
                "ndcg": ndcg_at_k(
                    trace.documents,
                    relevant_ids,
                    top_k,
                ),
                "hit": final_hit,
                "final_relevance": [
                    document_id in relevant_ids
                    for document_id in document_ids(trace.documents)
                ],
                "final_sources": [
                    document.metadata.get("source")
                    for document in trace.documents
                ],
                "filters": trace.filters,
                "timings_ms": trace.timings_ms,
                "rerank_fallback": trace.rerank_fallback,
            }
        )

    timing_keys = (
        "filter",
        "semantic",
        "bm25",
        "fusion",
        "rerank",
        "total",
    )
    summary = {
        f"semantic_recall@{candidate_count}": fmean(
            result["semantic_recall"] for result in results
        ),
        f"bm25_recall@{candidate_count}": fmean(
            result["bm25_recall"] for result in results
        ),
        f"hybrid_recall@{candidate_count}": fmean(
            result["hybrid_recall"] for result in results
        ),
        f"mrr@{top_k}": fmean(result["mrr"] for result in results),
        f"ndcg@{top_k}": fmean(result["ndcg"] for result in results),
        f"hit_rate@{top_k}": fmean(
            float(result["hit"]) for result in results
        ),
        "rerank_fallbacks": sum(
            int(result["rerank_fallback"]) for result in results
        ),
        "average_timings_ms": {
            key: round(
                fmean(result["timings_ms"][key] for result in results),
                2,
            )
            for key in timing_keys
        },
    }
    return {
        "case_count": len(cases),
        "candidate_count": candidate_count,
        "top_k": top_k,
        "summary": summary,
        "cases": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate PostgreSQL hybrid retrieval and reranking"
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
    )
    parser.add_argument("--candidate-count", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.0)
    parser.add_argument("--min-hit-rate", type=float, default=0.0)
    parser.add_argument("--case-id", action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_cases(args.cases)
    if args.case_id:
        requested_ids = set(args.case_id)
        cases = [case for case in cases if case.case_id in requested_ids]
        missing_ids = requested_ids - {case.case_id for case in cases}
        if missing_ids:
            raise ValueError(
                f"Unknown evaluation case ids: {sorted(missing_ids)}"
            )
    report = asyncio.run(
        evaluate(
            cases=cases,
            candidate_count=max(1, args.candidate_count),
            top_k=max(1, args.top_k),
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    summary = report["summary"]
    recall = summary[f"hybrid_recall@{report['candidate_count']}"]
    hit_rate = summary[f"hit_rate@{report['top_k']}"]
    if recall < args.min_recall or hit_rate < args.min_hit_rate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
