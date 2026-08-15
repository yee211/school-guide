from collections import Counter

from langchain_core.documents import Document

from app.rag.loader import load_knowledge_documents
from app.rag.metadata import (
    FilterCatalog,
    enrich_document_metadata,
    infer_retrieval_filters,
)
from app.rag.splitter import split_documents


def matches_filter(chunk: Document, filters: dict[str, list[str]]) -> bool:
    metadata = chunk.metadata
    for key in ("years", "subject_categories", "provinces", "majors"):
        if filters.get(key) and not (
            set(filters[key]) & set(metadata.get(key, []))
        ):
            return False
    return not filters.get("document_types") or metadata.get(
        "document_type"
    ) in filters["document_types"]


def main() -> None:
    sample = enrich_document_metadata(
        Document(
            page_content=(
                "2025年湖南省物理类人工智能专业最低投档分为500分。"
            ),
            metadata={"source": "录取分数线.md"},
        )
    )
    assert sample.metadata["years"] == ["2025"]
    assert sample.metadata["subject_categories"] == ["物理类"]
    assert sample.metadata["provinces"] == ["湖南省"]
    assert sample.metadata["majors"] == ["人工智能"]
    assert sample.metadata["document_type"] == "录取分数"

    catalog = FilterCatalog(
        years=("2024", "2025", "2026"),
        subject_categories=("物理类", "历史类"),
        provinces=("湖南省",),
        majors=("人工智能",),
        document_types=("录取分数", "招生计划"),
    )
    filters = infer_retrieval_filters(
        "2025年湖南省物理类人工智能专业录取线是多少？",
        catalog,
    )
    assert filters.as_dict() == {
        "years": ["2025"],
        "subject_categories": ["物理类"],
        "provinces": ["湖南省"],
        "majors": ["人工智能"],
        "document_types": ["录取分数"],
    }
    assert infer_retrieval_filters(
        "2023年人工智能专业招生计划",
        catalog,
    ).years == ("2023",)

    chunks = split_documents(load_knowledge_documents())
    required_keys = {
        "years",
        "subject_categories",
        "provinces",
        "majors",
        "document_type",
    }
    assert chunks
    assert all(required_keys <= chunk.metadata.keys() for chunk in chunks)
    filtered_counts = {}
    for query in (
        "图书馆的借阅规则是什么？",
        "宿舍是几人间，有空调吗？",
    ):
        query_filters = infer_retrieval_filters(query, catalog).as_dict()
        filtered_counts[query] = sum(
            matches_filter(chunk, query_filters)
            for chunk in chunks
        )
        assert filtered_counts[query] > 0, (
            query,
            query_filters,
        )

    type_counts = Counter(
        chunk.metadata["document_type"]
        for chunk in chunks
    )
    print(
        {
            "chunks": len(chunks),
            "document_types": dict(type_counts),
            "sample_filters": filters.as_dict(),
            "filtered_counts": filtered_counts,
        }
    )


if __name__ == "__main__":
    main()
