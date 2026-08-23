from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import jieba
import psycopg
from langchain_core.documents import Document
from pgvector import Vector
from psycopg import sql
from psycopg.types.json import Jsonb

from app.core.db import connect, PostgreSQLConfigurationError
from app.core.redis_cache import redis_cache
from app.rag.metadata import FilterCatalog, RetrievalFilters


logger = logging.getLogger(__name__)

REBUILD_LOCK_NAME = "school_knowledge_rebuild"


class PostgreSQLSchemaError(RuntimeError):
    """Raised when the existing knowledge schema is incompatible."""


@dataclass(frozen=True, slots=True)
class IndexSyncStats:
    total: int
    added: int
    removed: int


def inject_jieba_vocabulary(catalog: FilterCatalog | None = None) -> None:
    """向 jieba 注入学校专业、组号、简称等专有名词，防止 BM25 分词被切碎。"""
    core_words = (
        "长沙工业学院", "长工", "树达学院", "树达", "普通类", "物理类", "历史类",
        "艺术类", "单招", "专升本", "师范类", "公费师范生", "最低投档分", "最低分",
        "最高分", "控制线", "投档线", "录取分", "位次", "招生计划", "学费", "学制",
        "产教融合", "田径场", "图书馆", "宿舍", "空调"
    )
    for w in core_words:
        jieba.add_word(w, freq=10000)

    if catalog:
        for major in catalog.majors:
            if major:
                jieba.add_word(major, freq=10000)
        for group in catalog.groups:
            if group:
                jieba.add_word(group, freq=10000)
        for prov in catalog.provinces:
            if prov:
                jieba.add_word(prov, freq=10000)


def tokenize_for_search(text: str) -> list[str]:

    return [
        token
        for raw_token in jieba.cut_for_search(text.lower())
        if (
            (token := raw_token.strip())
            and any(character.isalnum() for character in token)
        )
    ]


def _documents_from_rows(
    rows: Sequence[dict],
) -> list[tuple[Document, float]]:
    return [
        (
            Document(
                page_content=row["content"],
                metadata=row["metadata"] or {},
            ),
            float(row["score"]),
        )
        for row in rows
    ]


def _metadata_filter_clause(
    filters: RetrievalFilters | None,
    table_alias: str,
) -> tuple[sql.Composable, list[object]]:
    if filters is None or filters.is_empty:
        return sql.SQL(""), []

    alias = sql.Identifier(table_alias)
    conditions: list[sql.Composable] = []
    parameters: list[object] = []
    array_filters = (
        ("years", filters.years),
        ("subject_categories", filters.subject_categories),
        ("provinces", filters.provinces),
        ("majors", filters.majors),
    )
    for metadata_key, values in array_filters:
        if not values:
            continue
        conditions.append(
            sql.SQL(
                "COALESCE({alias}.metadata -> {key}, '[]'::jsonb) "
                "?| ({values})::text[]"
            ).format(
                alias=alias,
                key=sql.Literal(metadata_key),
                values=sql.Placeholder(),
            )
        )
        parameters.append(list(values))

    if filters.document_types:
        conditions.append(
            sql.SQL(
                "COALESCE({alias}.metadata ->> 'document_type', '') "
                "= ANY(({values})::text[])"
            ).format(
                alias=alias,
                values=sql.Placeholder(),
            )
        )
        parameters.append(list(filters.document_types))

    if not conditions:
        return sql.SQL(""), []
    return (
        sql.SQL(" AND ") + sql.SQL(" AND ").join(conditions),
        parameters,
    )


class PostgreSQLKnowledgeStore:
    def _ensure_schema(
        self,
        connection: psycopg.Connection,
        vector_size: int,
    ) -> None:
        existing_type = connection.execute(
            """
            SELECT format_type(
                attribute.atttypid,
                attribute.atttypmod
            ) AS data_type
            FROM pg_attribute AS attribute
            WHERE attribute.attrelid = to_regclass(
                'public.school_knowledge_chunks'
            )
              AND attribute.attname = 'embedding'
              AND NOT attribute.attisdropped
            """
        ).fetchone()

        expected_type = f"vector({vector_size})"
        if existing_type and existing_type["data_type"] != expected_type:
            raise PostgreSQLSchemaError(
                "The existing pgvector dimension is "
                f"{existing_type['data_type']}, but the embedding model "
                f"returned {expected_type}. Drop the knowledge tables or use "
                "the original embedding model before rebuilding the index."
            )

        connection.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS public.school_knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT jsonb_build_object(),
                    embedding vector({vector_size}) NOT NULL,
                    token_count INTEGER NOT NULL CHECK (token_count >= 0),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ).format(vector_size=sql.SQL(str(vector_size)))
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS public.school_knowledge_chunk_terms (
                chunk_id TEXT NOT NULL REFERENCES
                    public.school_knowledge_chunks(id) ON DELETE CASCADE,
                term TEXT NOT NULL,
                term_frequency INTEGER NOT NULL CHECK (term_frequency > 0),
                PRIMARY KEY (chunk_id, term)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS school_knowledge_terms_term_idx
            ON public.school_knowledge_chunk_terms (term)
            """
        )
        for index_name, metadata_key in (
            ("school_knowledge_years_gin_idx", "years"),
            (
                "school_knowledge_subject_categories_gin_idx",
                "subject_categories",
            ),
            ("school_knowledge_provinces_gin_idx", "provinces"),
            ("school_knowledge_majors_gin_idx", "majors"),
        ):
            connection.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {index_name} "
                    "ON public.school_knowledge_chunks "
                    "USING gin ((metadata -> {metadata_key}))"
                ).format(
                    index_name=sql.Identifier(index_name),
                    metadata_key=sql.Literal(metadata_key),
                )
            )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS school_knowledge_document_type_idx
            ON public.school_knowledge_chunks ((metadata ->> 'document_type'))
            """
        )

    def list_ids(self) -> set[str]:
        try:
            with connect() as connection:
                rows = connection.execute(
                    "SELECT id FROM public.school_knowledge_chunks"
                ).fetchall()
        except psycopg.errors.UndefinedTable:
            return set()

        return {row["id"] for row in rows}

    def list_documents(self) -> list[Document]:
        try:
            with connect() as connection:
                rows = connection.execute(
                    """
                    SELECT content, metadata
                    FROM public.school_knowledge_chunks
                    ORDER BY id
                    """
                ).fetchall()
        except psycopg.errors.UndefinedTable:
            return []

        return [
            Document(
                page_content=row["content"],
                metadata=row["metadata"] or {},
            )
            for row in rows
        ]

    def get_filter_catalog(self) -> FilterCatalog:
        version = redis_cache.get_version()
        cache_key = f"rag:filter_catalog:{version}"
        cached = redis_cache.get_json(cache_key)
        if cached is not None:
            catalog = FilterCatalog(
                years=tuple(cached.get("years", ())),
                subject_categories=tuple(cached.get("subject_categories", ())),
                provinces=tuple(cached.get("provinces", ())),
                majors=tuple(cached.get("majors", ())),
                document_types=tuple(cached.get("document_types", ())),
            )
            inject_jieba_vocabulary(catalog)
            return catalog

        catalog = self._load_filter_catalog()
        inject_jieba_vocabulary(catalog)
        redis_cache.set_json(
            cache_key,
            {
                "years": list(catalog.years),
                "subject_categories": list(catalog.subject_categories),
                "provinces": list(catalog.provinces),
                "majors": list(catalog.majors),
                "document_types": list(catalog.document_types),
            },
        )
        return catalog


    def _load_filter_catalog(self) -> FilterCatalog:
        try:
            with connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        ARRAY(
                            SELECT DISTINCT jsonb_array_elements_text(
                                COALESCE(
                                    metadata -> 'years',
                                    '[]'::jsonb
                                )
                            )
                            FROM public.school_knowledge_chunks
                            ORDER BY 1
                        ) AS years,
                        ARRAY(
                            SELECT DISTINCT jsonb_array_elements_text(
                                COALESCE(
                                    metadata -> 'subject_categories',
                                    '[]'::jsonb
                                )
                            )
                            FROM public.school_knowledge_chunks
                            ORDER BY 1
                        ) AS subject_categories,
                        ARRAY(
                            SELECT DISTINCT jsonb_array_elements_text(
                                COALESCE(
                                    metadata -> 'provinces',
                                    '[]'::jsonb
                                )
                            )
                            FROM public.school_knowledge_chunks
                            ORDER BY 1
                        ) AS provinces,
                        ARRAY(
                            SELECT DISTINCT jsonb_array_elements_text(
                                COALESCE(
                                    metadata -> 'majors',
                                    '[]'::jsonb
                                )
                            )
                            FROM public.school_knowledge_chunks
                            ORDER BY 1
                        ) AS majors,
                        ARRAY(
                            SELECT DISTINCT metadata ->> 'document_type'
                            FROM public.school_knowledge_chunks
                            WHERE metadata ->> 'document_type' IS NOT NULL
                            ORDER BY 1
                        ) AS document_types
                    """
                ).fetchone()
        except psycopg.errors.UndefinedTable:
            return FilterCatalog()

        if row is None:
            return FilterCatalog()
        return FilterCatalog(
            years=tuple(row["years"] or ()),
            subject_categories=tuple(row["subject_categories"] or ()),
            provinces=tuple(row["provinces"] or ()),
            majors=tuple(row["majors"] or ()),
            document_types=tuple(row["document_types"] or ()),
        )


    def sync_documents(
        self,
        documents: Sequence[Document],
        embeddings: Sequence[Sequence[float]],
        ids: Sequence[str],
        desired_ids: Sequence[str],
    ) -> IndexSyncStats:
        if len(documents) != len(embeddings) or len(documents) != len(ids):
            raise ValueError("Documents, embeddings, and ids must have equal size")
        if not desired_ids:
            raise ValueError("The desired knowledge index cannot be empty")

        vector_size: int | None = None
        if embeddings:
            vector_size = len(embeddings[0])
            if vector_size <= 0 or any(
                len(embedding) != vector_size
                for embedding in embeddings
            ):
                raise ValueError(
                    "All embeddings must have the same non-zero size"
                )

        tokenized_documents = [
            tokenize_for_search(document.page_content)
            for document in documents
        ]
        chunk_rows = {
            chunk_id: (
                chunk_id,
                document.page_content.replace("\x00", ""),
                Jsonb(document.metadata),
                Vector(embedding),
                len(tokens),
            )
            for chunk_id, document, embedding, tokens in zip(
                ids,
                documents,
                embeddings,
                tokenized_documents,
                strict=True,
            )
        }
        term_rows = {
            chunk_id: [
                (chunk_id, term, frequency)
                for term, frequency in Counter(tokens).items()
            ]
            for chunk_id, tokens in zip(ids, tokenized_documents, strict=True)
        }
        desired_id_set = set(desired_ids)

        with connect() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (REBUILD_LOCK_NAME,),
            )
            if vector_size is not None:
                self._ensure_schema(connection, vector_size)

            current_rows = connection.execute(
                "SELECT id FROM public.school_knowledge_chunks"
            ).fetchall()
            current_ids = {row["id"] for row in current_rows}
            missing_embeddings = (
                desired_id_set - current_ids - set(chunk_rows)
            )
            if missing_embeddings:
                raise PostgreSQLSchemaError(
                    "The index changed during embedding generation; retry "
                    "the incremental sync"
                )

            obsolete_ids = current_ids - desired_id_set
            ids_to_insert = [
                chunk_id
                for chunk_id in ids
                if chunk_id not in current_ids
            ]

            if obsolete_ids:
                connection.execute(
                    """
                    DELETE FROM public.school_knowledge_chunks
                    WHERE id = ANY(%s)
                    """,
                    (list(obsolete_ids),),
                )

            if ids_to_insert:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO public.school_knowledge_chunks (
                            id,
                            content,
                            metadata,
                            embedding,
                            token_count
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        [chunk_rows[chunk_id] for chunk_id in ids_to_insert],
                    )
                    terms_to_insert = [
                        row
                        for chunk_id in ids_to_insert
                        for row in term_rows[chunk_id]
                    ]
                    if terms_to_insert:
                        cursor.executemany(
                            """
                            INSERT INTO public.school_knowledge_chunk_terms (
                                chunk_id,
                                term,
                                term_frequency
                            ) VALUES (%s, %s, %s)
                            ON CONFLICT (chunk_id, term) DO NOTHING
                            """,
                            terms_to_insert,
                        )

            try:
                with connection.transaction():
                    connection.execute(
                        """
                        CREATE INDEX IF NOT EXISTS
                            school_knowledge_embedding_hnsw_idx
                        ON public.school_knowledge_chunks
                        USING hnsw (embedding vector_cosine_ops)
                        """
                    )
            except psycopg.Error:
                logger.warning(
                    "Unable to create the pgvector HNSW index; exact vector "
                    "search remains available",
                    exc_info=True,
                )

        redis_cache.bump_version()
        return IndexSyncStats(
            total=len(desired_id_set),
            added=len(ids_to_insert),
            removed=len(obsolete_ids),
        )


    def semantic_search(
        self,
        query_embedding: Sequence[float],
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[tuple[Document, float]]:
        if top_k <= 0:
            return []

        filter_clause, filter_parameters = _metadata_filter_clause(
            filters,
            "chunk",
        )
        try:
            with connect() as connection:
                rows = connection.execute(
                    sql.SQL(
                        """
                    SELECT
                        chunk.id,
                        chunk.content,
                        chunk.metadata,
                        1 - (chunk.embedding <=> %s) AS score
                    FROM public.school_knowledge_chunks AS chunk
                    WHERE TRUE {filter_clause}
                    ORDER BY chunk.embedding <=> %s
                    LIMIT %s
                    """,
                    ).format(filter_clause=filter_clause),
                    [
                        Vector(query_embedding),
                        *filter_parameters,
                        Vector(query_embedding),
                        top_k,
                    ],
                ).fetchall()
        except psycopg.errors.UndefinedTable:
            return []

        return _documents_from_rows(rows)

    def bm25_search(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[tuple[Document, float]]:
        query_terms = list(dict.fromkeys(tokenize_for_search(query)))
        if not query_terms or top_k <= 0:
            return []

        filter_clause, filter_parameters = _metadata_filter_clause(
            filters,
            "candidate",
        )
        try:
            with connect() as connection:
                rows = connection.execute(
                    sql.SQL(
                        """
                    WITH filtered_chunks AS (
                        SELECT candidate.*
                        FROM public.school_knowledge_chunks AS candidate
                        WHERE TRUE {filter_clause}
                    ),
                    query_terms AS (
                        SELECT DISTINCT unnest(%s::text[]) AS term
                    ),
                    corpus AS (
                        SELECT
                            count(*)::double precision AS document_count,
                            avg(token_count)::double precision
                                AS avg_document_length
                        FROM filtered_chunks
                    ),
                    matching_terms AS (
                        SELECT
                            term_index.chunk_id,
                            term_index.term,
                            term_index.term_frequency::double precision
                                AS term_frequency,
                            count(*) OVER (
                                PARTITION BY term_index.term
                            )::double precision AS document_frequency
                        FROM public.school_knowledge_chunk_terms AS term_index
                        INNER JOIN query_terms
                            ON query_terms.term = term_index.term
                        INNER JOIN filtered_chunks AS eligible_chunk
                            ON eligible_chunk.id = term_index.chunk_id
                    )
                    SELECT
                        chunk.id,
                        chunk.content,
                        chunk.metadata,
                        sum(
                            ln(
                                1 + (
                                    corpus.document_count
                                    - matching_terms.document_frequency
                                    + 0.5
                                ) / (
                                    matching_terms.document_frequency + 0.5
                                )
                            ) * (
                                matching_terms.term_frequency * 2.2
                            ) / (
                                matching_terms.term_frequency
                                + 1.2 * (
                                    0.25
                                    + 0.75 * chunk.token_count
                                    / NULLIF(
                                        corpus.avg_document_length,
                                        0
                                    )
                                )
                            )
                        ) AS score
                    FROM matching_terms
                    INNER JOIN filtered_chunks AS chunk
                        ON chunk.id = matching_terms.chunk_id
                    CROSS JOIN corpus
                    GROUP BY
                        chunk.id,
                        chunk.content,
                        chunk.metadata,
                        corpus.document_count,
                        corpus.avg_document_length
                    ORDER BY score DESC, chunk.id
                    LIMIT %s
                    """,
                    ).format(filter_clause=filter_clause),
                    [*filter_parameters, query_terms, top_k],
                ).fetchall()
        except psycopg.errors.UndefinedTable:
            return []

        return _documents_from_rows(rows)


postgres_knowledge_store = PostgreSQLKnowledgeStore()
