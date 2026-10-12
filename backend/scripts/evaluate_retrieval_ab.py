"""Same-query semantic / RRF / reranked comparison, on the same indexed corpus."""
import argparse
import asyncio
from pathlib import Path
from statistics import fmean
from scripts.eval_quality import read_cases, write_report
from scripts.evaluate_retrieval import load_cases, is_relevant, recall_at_k, reciprocal_rank, ndcg_at_k

async def run(args):
    from app.rag.indexer import build_chunk_id
    from app.rag.postgres_store import postgres_knowledge_store
    from app.rag.retriever import retriever_service
    corpus = await asyncio.to_thread(postgres_knowledge_store.list_documents)
    if not corpus:
        raise ValueError("Knowledge index is empty")
    rows = []
    for case in load_cases(args.cases)[:args.limit]:
        relevant = {build_chunk_id(d) for d in corpus if is_relevant(d, case)}
        if not relevant:
            raise ValueError(f"No relevant chunks for {case.case_id}; check labels and splitting")
        trace = await retriever_service.search_with_trace(case.query, top_k=args.top_k,
                                                         candidate_count=args.candidates)
        stages = {"semantic": [d for d, _ in trace.semantic_results],
                  "rrf": trace.fused_candidates, "reranked": trace.documents}
        for mode, documents in stages.items():
            rows.append({"id": case.case_id, "mode": mode,
                         "recall": recall_at_k(documents, relevant, args.top_k),
                         "mrr": reciprocal_rank(documents, relevant, args.top_k),
                         "ndcg": ndcg_at_k(documents, relevant, args.top_k),
                         "hit": float(any(build_chunk_id(d) in relevant for d in documents[:args.top_k])),
                         "rerank_fallback": trace.rerank_fallback,
                         "filter_fallback": trace.filter_fallback, "timings_ms": trace.timings_ms})
    by_mode = {mode: {metric: fmean(r[metric] for r in rows if r["mode"] == mode)
                     for metric in ("recall", "mrr", "ndcg", "hit")} for mode in stages}
    write_report(args.output, rows, {"top_k": args.top_k, "candidates": args.candidates,
        "same_query_same_trace": True, "comparison": by_mode,
        "latency": "shared retrieval trace timings, not three independent end-to-end latency measurements",
        "labels": "source + keyword matching relevance; not human chunk annotations"})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path(__file__).resolve().parents[1] / Path("evals/retrieval_cases_extended.jsonl"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / Path("evals/reports/retrieval-ab.json"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidates", type=int, default=50)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if min(args.top_k, args.candidates, args.limit) < 1:
        parser.error("Counts must be positive")
    if args.candidates < args.top_k:
        parser.error("--candidates must be at least --top-k")
    if not args.live:
        print(f"Validated {len(read_cases(args.cases))} retrieval cases; no external calls.")
        return
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
