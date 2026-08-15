from app.rag.metadata import infer_retrieval_filters
from app.rag.postgres_store import _connect, postgres_knowledge_store


def main() -> None:
    with _connect() as connection:
        identity = connection.execute(
            """
            SELECT
                current_database() AS database_name,
                current_user AS user_name,
                roles.rolsuper AS is_superuser
            FROM pg_roles AS roles
            WHERE roles.rolname = current_user
            """
        ).fetchone()
        chunk_count = connection.execute(
            """
            SELECT count(*) AS count
            FROM public.school_knowledge_chunks
            """
        ).fetchone()["count"]
        term_count = connection.execute(
            """
            SELECT count(*) AS count
            FROM public.school_knowledge_chunk_terms
            """
        ).fetchone()["count"]
        vector_type = connection.execute(
            """
            SELECT format_type(atttypid, atttypmod) AS data_type
            FROM pg_attribute
            WHERE attrelid = 'public.school_knowledge_chunks'::regclass
              AND attname = 'embedding'
            """
        ).fetchone()["data_type"]
        indexes = [
            row["indexname"]
            for row in connection.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename IN (
                    'school_knowledge_chunks',
                    'school_knowledge_chunk_terms'
                )
                ORDER BY indexname
                """
            ).fetchall()
        ]

    catalog = postgres_knowledge_store.get_filter_catalog()
    filters = infer_retrieval_filters(
        "2025年湖南省物理类人工智能专业录取线",
        catalog,
    )
    lexical_results = postgres_knowledge_store.bm25_search(
        "2025年湖南省物理类人工智能专业录取线",
        5,
        filters,
    )

    assert chunk_count > 0
    assert term_count > 0
    assert vector_type == "vector(1024)"
    assert identity["database_name"] == "school_assistant"
    assert identity["user_name"] == "school_assistant_app"
    assert not identity["is_superuser"]
    assert "school_knowledge_embedding_hnsw_idx" in indexes
    assert "school_knowledge_years_gin_idx" in indexes
    assert "school_knowledge_subject_categories_gin_idx" in indexes
    assert "school_knowledge_provinces_gin_idx" in indexes
    assert "school_knowledge_majors_gin_idx" in indexes
    assert "school_knowledge_document_type_idx" in indexes
    assert lexical_results
    assert catalog.years
    assert all(
        "2025" in result.metadata.get("years", [])
        and "物理类" in result.metadata.get("subject_categories", [])
        and "湖南省" in result.metadata.get("provinces", [])
        and "人工智能" in result.metadata.get("majors", [])
        and result.metadata.get("document_type") == "录取分数"
        for result, _ in lexical_results
    )

    print(
        {
            "chunks": chunk_count,
            "terms": term_count,
            "vector_type": vector_type,
            "database": identity["database_name"],
            "user": identity["user_name"],
            "is_superuser": identity["is_superuser"],
            "indexes": indexes,
            "filters": filters.as_dict(),
            "bm25_results": len(lexical_results),
        }
    )


if __name__ == "__main__":
    main()
