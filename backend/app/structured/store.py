"""结构化数据（录取分数 / 招生计划）的建表与全量重建。"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from app.core.redis_cache import redis_cache
from app.core.db import connect

logger = logging.getLogger(__name__)

_SCORE_COLUMNS = (
    "year",
    "province",
    "subject_category",
    "group_no",
    "major",
    "score_type",
    "score",
    "admission_rank",
    "batch",
    "source_file",
)

_PLAN_COLUMNS = (
    "year",
    "province",
    "subject_category",
    "group_no",
    "major",
    "plan",
    "tuition",
    "duration",
    "major_code",
    "subject_requirement",
    "batch",
    "source_file",
)

_SCORE_INSERT = (
    "INSERT INTO public.school_admission_scores ("
    + ", ".join(_SCORE_COLUMNS)
    + ") VALUES ("
    + ", ".join(["%s"] * len(_SCORE_COLUMNS))
    + ")"
)

_PLAN_INSERT = (
    "INSERT INTO public.school_admission_plans ("
    + ", ".join(_PLAN_COLUMNS)
    + ") VALUES ("
    + ", ".join(["%s"] * len(_PLAN_COLUMNS))
    + ")"
)


def _ensure_schema(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS public.school_admission_scores (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            year           SMALLINT       NOT NULL CHECK (year BETWEEN 2000 AND 2100),
            province       TEXT           NOT NULL,
            subject_category TEXT         NOT NULL,
            group_no       TEXT,
            major          TEXT,
            score_type     TEXT           NOT NULL,
            score          NUMERIC(7,2)   NOT NULL,
            admission_rank INTEGER,
            batch          TEXT,
            source_file    TEXT           NOT NULL,
            updated_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS public.school_admission_plans (
            id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            year                SMALLINT       NOT NULL CHECK (year BETWEEN 2000 AND 2100),
            province            TEXT           NOT NULL,
            subject_category    TEXT           NOT NULL,
            group_no            TEXT,
            major               TEXT,
            plan                INTEGER        NOT NULL,
            tuition             NUMERIC(10,2),
            duration            SMALLINT,
            major_code          TEXT,
            subject_requirement TEXT,
            batch               TEXT,
            source_file         TEXT           NOT NULL,
            updated_at          TIMESTAMPTZ    NOT NULL DEFAULT now()
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS school_admission_scores_natural_key
        ON public.school_admission_scores (
            year, province, subject_category,
            COALESCE(group_no, ''), COALESCE(major, ''),
            score_type, COALESCE(batch, ''), source_file
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS school_admission_plans_natural_key
        ON public.school_admission_plans (
            year, province, subject_category,
            COALESCE(group_no, ''), COALESCE(major, ''), source_file
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS school_admission_scores_lookup
        ON public.school_admission_scores (year, province, subject_category, score_type)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS school_admission_scores_major
        ON public.school_admission_scores (major)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS school_admission_plans_lookup
        ON public.school_admission_plans (year, province, subject_category)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS school_admission_plans_major
        ON public.school_admission_plans (major)
        """
    )


def _score_tuple(row: dict) -> tuple:
    return tuple(row.get(col) for col in _SCORE_COLUMNS)


def _plan_tuple(row: dict) -> tuple:
    return tuple(row.get(col) for col in _PLAN_COLUMNS)


def reload(
    score_rows: Sequence[dict],
    plan_rows: Sequence[dict],
) -> tuple[int, int]:
    """全量重建两张表（单事务 DELETE + INSERT，幂等）。"""
    # 防御：跳过科类为空的脏行
    score_rows = [
        row for row in score_rows
        if row.get("subject_category") and row.get("score") is not None
    ]
    plan_rows = [
        row for row in plan_rows
        if row.get("subject_category") and row.get("plan") is not None
    ]

    with connect() as connection:
        _ensure_schema(connection)

        connection.execute("DELETE FROM public.school_admission_scores")
        connection.execute("DELETE FROM public.school_admission_plans")

        if score_rows:
            with connection.cursor() as cursor:
                cursor.executemany(
                    _SCORE_INSERT,
                    [_score_tuple(row) for row in score_rows],
                )
        if plan_rows:
            with connection.cursor() as cursor:
                cursor.executemany(
                    _PLAN_INSERT,
                    [_plan_tuple(row) for row in plan_rows],
                )

    # 数据已提交，使所有结构化查询缓存失效（下次请求重建）
    redis_cache.bump_version()

    logger.info(
        "Structured data reloaded: scores=%d plans=%d",
        len(score_rows),
        len(plan_rows),
    )
    return len(score_rows), len(plan_rows)
