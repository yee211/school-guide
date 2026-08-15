"""Markdown 表格解析与规整工具。"""
from __future__ import annotations

import re

from app.structured.normalize import normalize_province

_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


def parse_pipe_table(text: str) -> tuple[list[str], list[list[str]]]:
    """解析标准 Markdown pipe 表格，返回 ``(header, rows)``。

    跳过分隔行（``:---``）。不处理 markdown 加粗标记（``**x**``），由调用方清理。
    """
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("|")
    ]
    if not lines:
        return [], []

    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows: list[list[str]] = []
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        # 分隔行：所有非空单元格都形如 :---
        if cells and all(
            _SEPARATOR_CELL.fullmatch(cell) for cell in cells if cell
        ):
            continue
        rows.append(cells)
    return header, rows


def forward_fill(
    rows: list[list[str]],
    columns: set[int],
) -> list[list[str]]:
    """对指定列索引做前向填充：空单元格沿用上方最近的非空值。

    用于处理合并单元格（科类/组别/最高分/投档分等只在组首行出现）。
    """
    filled = [row[:] for row in rows]
    for col in columns:
        last = ""
        for row in filled:
            if col < len(row):
                cell = row[col].strip()
                if cell:
                    last = cell
                else:
                    row[col] = last
    return filled


def transpose_cross_table(
    header: list[str],
    rows: list[list[str]],
) -> list[tuple[str, str, int]]:
    """把「专业 × 省份」交叉表转置为 ``(专业, 省份, 计划数)`` 三元组。

    ``header[0]`` 是专业列头，``header[1:]`` 是省份列。
    跳过合计/总计/分隔行，跳过无法归一为省份的列，空单元格不产出。
    """
    result: list[tuple[str, str, int]] = []
    provinces: list[str] = []
    for raw in header[1:]:
        normalized = normalize_province(raw)
        if normalized is None:
            # 保留 None 占位，保证列索引对齐，后续跳过
            provinces.append("")
        else:
            provinces.append(normalized)

    for row in rows:
        if not row:
            continue
        major = (row[0] or "").strip()
        if not major or any(
            key in major for key in ("合计", "总计", "★", "△", "⊕")
        ):
            continue
        for idx, province in enumerate(provinces, start=1):
            if not province:
                continue
            if idx < len(row):
                value = (row[idx] or "").strip()
                if value.isdigit():
                    result.append((major, province, int(value)))
    return result


def parse_section_metadata(text: str) -> dict[str, str]:
    """解析分节文件节头里的 ``- **科类**：普通类(首选物理)`` 等键值对。"""
    meta: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"-\s*\*\*([^*]+)\*\*[:：]\s*(.*)", line.strip())
        if match:
            meta[match.group(1).strip()] = match.group(2).strip()
    return meta


def strip_markdown_bold(cell: str) -> str:
    """去掉 markdown 加粗标记 ``**x**``。"""
    return re.sub(r"\*\*", "", cell or "").strip()
