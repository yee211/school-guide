"""结构化数据抽取用的归一化与数值解析工具。

复用 ``app.rag.metadata`` 里的别名表，避免复制两份。
"""
from __future__ import annotations

import re

from app.rag.metadata import PROVINCE_ALIASES, SUBJECT_ALIASES

# 专业名归一：该校「数学与应用数学」与「数学与应用数学（师范类）」是同一专业。
MAJOR_ALIASES = {
    "数学与应用数学": "数学与应用数学（师范类）",
}

_SUBJECT_SHORT = {
    "物理类": "物理",
    "历史类": "历史",
    "艺术类": "艺术",
}

_GROUP_PREFIX_PATTERN = re.compile(r"(物理|历史|艺术)")
_GROUP_NUM_PATTERN = re.compile(r"(\d{3})")

_EMPTY_CELLS = {"", "/", "-", "—", "－", "–", "--"}


def normalize_subject(raw: str) -> str | None:
    """把科类原文归一为 物理类/历史类/艺术类。"""
    raw = (raw or "").strip()
    if not raw:
        return None
    for category, aliases in SUBJECT_ALIASES.items():
        if any(alias in raw for alias in aliases):
            return category
    return None


def normalize_province(raw: str) -> str | None:
    """把省份简称/全称归一为全称；无法识别或非省份（合计列等）返回 None。"""
    raw = (raw or "").strip()
    if not raw or any(k in raw for k in ("合计", "总计", "计划", "专业")):
        return None
    if raw in PROVINCE_ALIASES:
        return PROVINCE_ALIASES[raw]
    if raw.endswith(("省", "自治区", "特别行政区")):
        return raw
    return None


def normalize_major(raw: str) -> str:
    """归一专业名：半角/全角括号统一，再把 数学与应用数学 合并到（师范类）。"""
    raw = (raw or "").strip()
    raw = raw.replace("(", "（").replace(")", "）")
    return MAJOR_ALIASES.get(raw, raw)


def normalize_group(raw: str, subject: str | None = None) -> str | None:
    """归一专业组号，如 ``物理103组``。

    裸 ``103组`` / ``第103组`` 靠 subject（物理类/历史类/艺术类）补前缀；
    补不出前缀时返回裸 ``103组``，由查询层用 LIKE 兜底。
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    num_match = _GROUP_NUM_PATTERN.search(raw)
    if not num_match:
        return None
    num = num_match.group(1)

    short = _SUBJECT_SHORT.get(subject or "")
    if not short:
        prefix_match = _GROUP_PREFIX_PATTERN.search(raw)
        if prefix_match:
            short = prefix_match.group(1)
    if not short:
        return f"{num}组"
    return f"{short}{num}组"


def parse_score_rank(cell: str) -> tuple[float | None, int | None]:
    """解析 ``465 (132431)`` / ``515分（位次86215）`` / ``279.9`` 等单元格。

    返回 ``(score, rank)``，艺术类综合分无位次时 rank 为 None。
    """
    cell = (cell or "").strip()
    if cell in _EMPTY_CELLS:
        return None, None

    score_match = re.search(r"(\d+(?:\.\d+)?)", cell)
    score = float(score_match.group(1)) if score_match else None

    rank_match = re.search(r"位\s*次\s*(\d+)", cell) or re.search(
        r"[（(]\s*(\d+)\s*[)）]", cell
    )
    rank = int(rank_match.group(1)) if rank_match else None

    return score, rank
