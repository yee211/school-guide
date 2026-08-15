"""结构化精确查询：把 ``infer_retrieval_filters`` 的结果转成 SQL 查两张表。"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from langchain_core.tools import tool
from psycopg import sql

from app.core.redis_cache import redis_cache
from app.rag.metadata import (
    FilterCatalog,
    RetrievalFilters,
    infer_retrieval_filters,
)
from app.rag.postgres_store import connect

logger = logging.getLogger(__name__)


@dataclass
class StructuredResult:
    score_rows: list[dict] = field(default_factory=list)
    plan_rows: list[dict] = field(default_factory=list)
    source_files: tuple[str, ...] = ()
    is_targeted: bool = False

    def format_context(self) -> str:
        if not self.score_rows and not self.plan_rows:
            return "未查询到符合条件的结构化数据。"

        parts: list[str] = []
        if self.score_rows:
            lines = [
                "【录取分数 / 投档线】",
                "| 年份 | 省份 | 科类 | 专业组 | 专业 | 类型 | 分数 | 位次 | 来源 |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
            for row in self.score_rows:
                major = row["major"] or "（组）"
                rank = row["admission_rank"] if row["admission_rank"] is not None else ""
                src = (row["source_file"] or "").split("/")[-1]
                lines.append(
                    f"| {row['year']} | {row['province']} | {row['subject_category']} "
                    f"| {row['group_no'] or ''} | {major} | {row['score_type']} "
                    f"| {row['score']} | {rank} | {src} |"
                )
            parts.append("\n".join(lines))

        if self.plan_rows:
            lines = [
                "【招生计划】",
                "| 年份 | 省份 | 科类 | 专业组 | 专业 | 计划数 | 学费 | 学制 | 来源 |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
            for row in self.plan_rows:
                major = row["major"] or "（组）"
                tuition = row["tuition"] if row["tuition"] is not None else ""
                duration = row["duration"] if row["duration"] is not None else ""
                src = (row["source_file"] or "").split("/")[-1]
                lines.append(
                    f"| {row['year']} | {row['province']} | {row['subject_category']} "
                    f"| {row['group_no'] or ''} | {major} | {row['plan']} "
                    f"| {tuition} | {duration} | {src} |"
                )
            parts.append("\n".join(lines))

        if self.source_files:
            parts.append(f"数据来源：{', '.join(self.source_files)}")
        return "\n\n".join(parts)


class StructuredQueryService:
    def get_catalog(self) -> FilterCatalog:
        version = redis_cache.get_version()
        cache_key = f"structured:catalog:{version}"
        cached = redis_cache.get_json(cache_key)
        if cached is not None:
            return self._catalog_from_dict(cached)

        catalog = self._load_catalog()
        redis_cache.set_json(cache_key, self._catalog_to_dict(catalog))
        return catalog

    def _load_catalog(self) -> FilterCatalog:
        with connect() as connection:
            row = connection.execute(
                """
                WITH combined AS (
                    SELECT year, province, subject_category, group_no, major
                    FROM public.school_admission_scores
                    UNION ALL
                    SELECT year, province, subject_category, group_no, major
                    FROM public.school_admission_plans
                )
                SELECT
                    array_agg(DISTINCT year ORDER BY year) AS years,
                    array_agg(DISTINCT subject_category ORDER BY subject_category)
                        AS subject_categories,
                    array_agg(DISTINCT province ORDER BY province) AS provinces,
                    array_agg(DISTINCT major ORDER BY major)
                        FILTER (WHERE major IS NOT NULL) AS majors,
                    array_agg(DISTINCT group_no ORDER BY group_no)
                        FILTER (WHERE group_no IS NOT NULL) AS groups
                FROM combined
                """
            ).fetchone()

        if row is None:
            return FilterCatalog()

        return FilterCatalog(
            years=tuple(str(y) for y in (row["years"] or ())),
            subject_categories=tuple(row["subject_categories"] or ()),
            provinces=tuple(row["provinces"] or ()),
            majors=tuple(row["majors"] or ()),
            document_types=("录取分数", "招生计划"),
            groups=tuple(row["groups"] or ()),
        )

    @staticmethod
    def _catalog_to_dict(catalog: FilterCatalog) -> dict:
        return {
            "years": list(catalog.years),
            "subject_categories": list(catalog.subject_categories),
            "provinces": list(catalog.provinces),
            "majors": list(catalog.majors),
            "document_types": list(catalog.document_types),
            "groups": list(catalog.groups),
        }

    @staticmethod
    def _catalog_from_dict(data: dict) -> FilterCatalog:
        return FilterCatalog(
            years=tuple(data.get("years", ())),
            subject_categories=tuple(data.get("subject_categories", ())),
            provinces=tuple(data.get("provinces", ())),
            majors=tuple(data.get("majors", ())),
            document_types=tuple(data.get("document_types", ())),
            groups=tuple(data.get("groups", ())),
        )

    @staticmethod
    def _infer_score_type(question: str) -> str | None:
        if "最高" in question:
            return "最高分"
        if "控制线" in question:
            return "控制线"
        if any(
            key in question
            for key in ("最低", "投档", "录取线", "分数线", "录取分", "分数")
        ):
            return "最低分"
        return None

    @staticmethod
    def _build_where(
        filters: RetrievalFilters,
        table_alias: str,
        score_type: str | None = None,
    ) -> tuple[sql.Composable, list]:
        alias = sql.Identifier(table_alias)
        conditions: list[sql.Composable] = []
        params: list = []

        if filters.years:
            conditions.append(sql.SQL("{}.year = ANY(%s)").format(alias))
            params.append([int(y) for y in filters.years])
        if filters.subject_categories:
            conditions.append(
                sql.SQL("{}.subject_category = ANY(%s)").format(alias)
            )
            params.append(list(filters.subject_categories))
        if filters.provinces:
            conditions.append(sql.SQL("{}.province = ANY(%s)").format(alias))
            params.append(list(filters.provinces))
        if filters.majors:
            conditions.append(sql.SQL("{}.major = ANY(%s)").format(alias))
            params.append(list(filters.majors))
        if filters.groups:
            exact = [g for g in filters.groups if not g[0].isdigit()]
            fuzzy = [g for g in filters.groups if g[0].isdigit()]
            if exact:
                conditions.append(sql.SQL("{}.group_no = ANY(%s)").format(alias))
                params.append(exact)
            if fuzzy:
                conditions.append(
                    sql.SQL("{}.group_no LIKE ANY(%s)").format(alias)
                )
                params.append([f"%{g}" for g in fuzzy])
        if score_type:
            conditions.append(sql.SQL("{}.score_type = %s").format(alias))
            params.append(score_type)

        if not conditions:
            return sql.SQL(""), []
        return sql.SQL(" AND ") + sql.SQL(" AND ").join(conditions), params

    def _query_scores(
        self,
        filters: RetrievalFilters,
        score_type: str | None,
    ) -> list[dict]:
        where, params = self._build_where(filters, "s", score_type)
        with connect() as connection:
            rows = connection.execute(
                sql.SQL(
                    """
                    SELECT year, province, subject_category, group_no, major,
                           score_type, score, admission_rank, batch, source_file
                    FROM public.school_admission_scores AS s
                    WHERE TRUE {where}
                    ORDER BY year DESC, score DESC, major NULLS LAST
                    """
                ).format(where=where),
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _query_plans(self, filters: RetrievalFilters) -> list[dict]:
        where, params = self._build_where(filters, "p")
        with connect() as connection:
            rows = connection.execute(
                sql.SQL(
                    """
                    SELECT year, province, subject_category, group_no, major,
                           plan, tuition, duration, major_code,
                           subject_requirement, batch, source_file
                    FROM public.school_admission_plans AS p
                    WHERE TRUE {where}
                    ORDER BY year DESC, plan DESC, major NULLS LAST
                    """
                ).format(where=where),
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def query(
        self,
        filters: RetrievalFilters,
        score_type: str | None = None,
    ) -> StructuredResult:
        is_targeted = bool(filters.years or filters.majors or filters.groups)
        if not is_targeted:
            return StructuredResult(is_targeted=False)

        cache_key = self._cache_key(filters, score_type)
        cached = redis_cache.get_json(cache_key)
        if cached is not None:
            return StructuredResult(
                score_rows=cached["score_rows"],
                plan_rows=cached["plan_rows"],
                source_files=tuple(cached["source_files"]),
                is_targeted=True,
            )

        result = self._query_db(filters, score_type)
        redis_cache.set_json(
            cache_key,
            {
                "score_rows": result.score_rows,
                "plan_rows": result.plan_rows,
                "source_files": list(result.source_files),
            },
        )
        return result

    def _cache_key(
        self,
        filters: RetrievalFilters,
        score_type: str | None,
    ) -> str:
        version = redis_cache.get_version()
        raw = json.dumps(
            {"filters": filters.as_dict(), "score_type": score_type},
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return f"structured:query:{version}:{digest}"

    def _query_db(
        self,
        filters: RetrievalFilters,
        score_type: str | None,
    ) -> StructuredResult:
        want_scores = not filters.document_types or "录取分数" in filters.document_types
        want_plans = not filters.document_types or "招生计划" in filters.document_types

        score_rows = self._query_scores(filters, score_type) if want_scores else []
        plan_rows = self._query_plans(filters) if want_plans else []

        source_files = tuple(
            dict.fromkeys(
                row["source_file"]
                for row in score_rows + plan_rows
                if row.get("source_file")
            )
        )

        return StructuredResult(
            score_rows=score_rows,
            plan_rows=plan_rows,
            source_files=source_files,
            is_targeted=True,
        )

    def query_and_format(self, question: str) -> StructuredResult:
        catalog = self.get_catalog()
        filters = infer_retrieval_filters(question, catalog)
        score_type = self._infer_score_type(question)
        result = self.query(filters, score_type)
        logger.info(
            "Structured query filters=%s score_type=%s scores=%d plans=%d",
            filters.as_dict(),
            score_type,
            len(result.score_rows),
            len(result.plan_rows),
        )
        return result


structured_query_service = StructuredQueryService()


@tool
def query_admission_data(question: str) -> str:
    """查询长沙工业学院的录取分数、投档线、位次、招生计划数、学费等结构化数据。

    当用户询问具体某年/某省份/某科类/某专业（或某专业组）的
    分数线、位次、录取分数、招生计划人数、学费时，调用此工具。
    参数 question 是用户的问题原文。
    """
    return structured_query_service.query_and_format(question).format_context()
