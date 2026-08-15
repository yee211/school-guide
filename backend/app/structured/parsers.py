"""7 个结构化 Markdown 文件的解析器。

每个解析器返回 ``(score_rows, plan_rows)``，行 dict 的键与两张表列名一一对应。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.structured.markdown_tables import (
    forward_fill,
    parse_pipe_table,
    parse_section_metadata,
    strip_markdown_bold,
    transpose_cross_table,
)
from app.structured.normalize import (
    normalize_group,
    normalize_major,
    normalize_province,
    normalize_subject,
    parse_score_rank,
)

RAW_PREFIX = "data/raw/"

_EMPTY = {"", "/", "-", "—", "－", "–", "--", "－"}


def _parse_int(cell: str) -> int | None:
    cell = strip_markdown_bold(cell or "").strip()
    if cell in _EMPTY:
        return None
    match = re.search(r"(\d+)", cell)
    return int(match.group(1)) if match else None


def _score_row(
    *,
    year: int,
    province: str,
    subject_category: str,
    score_type: str,
    score: float,
    admission_rank: int | None,
    group_no: str | None = None,
    major: str | None = None,
    batch: str | None = None,
    source_file: str,
) -> dict:
    return {
        "year": year,
        "province": province,
        "subject_category": subject_category,
        "group_no": group_no,
        "major": major,
        "score_type": score_type,
        "score": score,
        "admission_rank": admission_rank,
        "batch": batch,
        "source_file": source_file,
    }


def _plan_row(
    *,
    year: int,
    province: str,
    subject_category: str,
    plan: int,
    group_no: str | None = None,
    major: str | None = None,
    tuition: int | None = None,
    duration: int | None = None,
    major_code: str | None = None,
    subject_requirement: str | None = None,
    batch: str | None = None,
    source_file: str,
) -> dict:
    return {
        "year": year,
        "province": province,
        "subject_category": subject_category,
        "group_no": group_no,
        "major": major,
        "plan": plan,
        "tuition": tuition,
        "duration": duration,
        "major_code": major_code,
        "subject_requirement": subject_requirement,
        "batch": batch,
        "source_file": source_file,
    }


def _split_headings(text: str) -> list[tuple[str, str]]:
    """按 markdown 标题（#/##/###）切分，返回 ``[(标题, 内容)]``。"""
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^#{1,3}\s+", line):
            if current_lines or current_title:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = line.strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or current_title:
        sections.append((current_title, "\n".join(current_lines)))
    return sections


# ---------------------------------------------------------------------------
# 文件1：CIT2425省内投档线.md —— 专业粒度，2024/2025 计划数 + 分数线位次
# ---------------------------------------------------------------------------
def parse_cit2425(text: str, source_file: str) -> tuple[list[dict], list[dict]]:
    _, rows = parse_pipe_table(text)
    score_rows: list[dict] = []
    plan_rows: list[dict] = []

    for row in rows:
        if len(row) < 6:
            continue
        subject = normalize_subject(row[0])
        major = normalize_major(row[1])
        if not subject or not major:
            continue

        for year, col in ((2024, 2), (2025, 3)):
            plan = _parse_int(row[col])
            if plan is not None:
                plan_rows.append(
                    _plan_row(
                        year=year,
                        province="湖南省",
                        subject_category=subject,
                        plan=plan,
                        major=major,
                        source_file=source_file,
                    )
                )

        for year, col in ((2024, 4), (2025, 5)):
            score, rank = parse_score_rank(row[col])
            if score is not None:
                score_rows.append(
                    _score_row(
                        year=year,
                        province="湖南省",
                        subject_category=subject,
                        score_type="最低分",
                        score=score,
                        admission_rank=rank,
                        major=major,
                        source_file=source_file,
                    )
                )

    return score_rows, plan_rows


# ---------------------------------------------------------------------------
# 文件2：CIT2026省内投档线.md —— 专业组粒度，每专业一行（组分数重复）
# ---------------------------------------------------------------------------
def parse_cit2026(text: str, source_file: str) -> tuple[list[dict], list[dict]]:
    _, rows = parse_pipe_table(text)
    score_rows: list[dict] = []
    plan_rows: list[dict] = []

    for row in rows:
        if len(row) < 6:
            continue
        subject = normalize_subject(row[0])
        group_no = normalize_group(row[1], subject)
        major = normalize_major(row[2])
        if not subject:
            continue

        plan = _parse_int(row[3])
        if plan is not None and major:
            plan_rows.append(
                _plan_row(
                    year=2026,
                    province="湖南省",
                    subject_category=subject,
                    plan=plan,
                    group_no=group_no,
                    major=major,
                    source_file=source_file,
                )
            )

        max_score, max_rank = parse_score_rank(row[4])
        if max_score is not None:
            score_rows.append(
                _score_row(
                    year=2026,
                    province="湖南省",
                    subject_category=subject,
                    score_type="最高分",
                    score=max_score,
                    admission_rank=max_rank,
                    group_no=group_no,
                    major=major,
                    source_file=source_file,
                )
            )

        min_score, min_rank = parse_score_rank(row[5])
        if min_score is not None:
            score_rows.append(
                _score_row(
                    year=2026,
                    province="湖南省",
                    subject_category=subject,
                    score_type="最低分",
                    score=min_score,
                    admission_rank=min_rank,
                    group_no=group_no,
                    major=major,
                    source_file=source_file,
                )
            )

    return score_rows, plan_rows


# ---------------------------------------------------------------------------
# 文件3：长沙工业学院历年录取分数线汇总.md
# ---------------------------------------------------------------------------
def _parse_summary_province(
    content: str,
    year: int,
    province: str,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    """省内表：列 = 科类0/组别1/专业2/计划数3/最高分4/投档分5。

    只对科类/组别做前向填充；最高分/投档分是专业级数据，缺失即缺失，不填充。
    """
    _, rows = parse_pipe_table(content)
    if not rows:
        return [], []

    filled = forward_fill(rows, {0, 1})
    score_rows: list[dict] = []
    plan_rows: list[dict] = []

    for row in filled:
        subject = normalize_subject(strip_markdown_bold(row[0]))
        group_no = normalize_group(strip_markdown_bold(row[1]), subject)
        major = normalize_major(strip_markdown_bold(row[2]))
        if not subject or not major or major in {"专业", "招生专业"}:
            continue

        plan = _parse_int(row[3])
        if plan is not None:
            plan_rows.append(
                _plan_row(
                    year=year,
                    province=province,
                    subject_category=subject,
                    plan=plan,
                    group_no=group_no,
                    major=major,
                    source_file=source_file,
                )
            )

        max_score, max_rank = parse_score_rank(row[4])
        if max_score is not None:
            score_rows.append(
                _score_row(
                    year=year,
                    province=province,
                    subject_category=subject,
                    score_type="最高分",
                    score=max_score,
                    admission_rank=max_rank,
                    group_no=group_no,
                    major=major,
                    source_file=source_file,
                )
            )

        min_score, min_rank = parse_score_rank(row[5])
        if min_score is not None:
            score_rows.append(
                _score_row(
                    year=year,
                    province=province,
                    subject_category=subject,
                    score_type="最低分",
                    score=min_score,
                    admission_rank=min_rank,
                    group_no=group_no,
                    major=major,
                    source_file=source_file,
                )
            )

    return score_rows, plan_rows


def _parse_summary_outprovince(
    content: str,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    """省外表：列 = 省份0/科类1/招生专业2/计划数3/最高分4/投档线5/控制线6。

    只对省份/科类/控制线做前向填充；最高分/投档线是专业级数据，缺失即缺失。
    控制线是省控线（省份+科类统一），可安全填充。
    """
    _, rows = parse_pipe_table(content)
    if not rows:
        return [], []

    filled = forward_fill(rows, {0, 1, 6})
    score_rows: list[dict] = []
    plan_rows: list[dict] = []

    for row in filled:
        province = normalize_province(strip_markdown_bold(row[0]))
        subject = normalize_subject(strip_markdown_bold(row[1]))
        major = normalize_major(strip_markdown_bold(row[2]))
        if not province or not subject or not major or major in {"专业", "招生专业"}:
            continue

        plan = _parse_int(row[3])
        if plan is not None:
            plan_rows.append(
                _plan_row(
                    year=2025,
                    province=province,
                    subject_category=subject,
                    plan=plan,
                    major=major,
                    source_file=source_file,
                )
            )

        max_score, max_rank = parse_score_rank(row[4])
        if max_score is not None:
            score_rows.append(
                _score_row(
                    year=2025,
                    province=province,
                    subject_category=subject,
                    score_type="最高分",
                    score=max_score,
                    admission_rank=max_rank,
                    major=major,
                    source_file=source_file,
                )
            )

        min_score, min_rank = parse_score_rank(row[5])
        if min_score is not None:
            score_rows.append(
                _score_row(
                    year=2025,
                    province=province,
                    subject_category=subject,
                    score_type="最低分",
                    score=min_score,
                    admission_rank=min_rank,
                    major=major,
                    source_file=source_file,
                )
            )

        ctrl_score, _ = parse_score_rank(row[6])
        if ctrl_score is not None:
            score_rows.append(
                _score_row(
                    year=2025,
                    province=province,
                    subject_category=subject,
                    score_type="控制线",
                    score=ctrl_score,
                    admission_rank=None,
                    major=major,
                    source_file=source_file,
                )
            )

    return score_rows, plan_rows


def _parse_control_lines(
    content: str,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    """2026 控制线表（两行 header），列：类别0/历史文化1/历史专业2/物理文化3/物理专业4。"""
    score_rows: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [strip_markdown_bold(c.strip()) for c in line.strip("|").split("|")]
        if not cells or cells[0] in {"专业类别", "项目", ""}:
            continue
        if re.fullmatch(r":?-{3,}:?", cells[0] or ""):
            continue
        batch = cells[0]
        if len(cells) >= 5:
            hist = parse_score_rank(cells[1])[0]
            phys = parse_score_rank(cells[3])[0]
            if hist is not None:
                score_rows.append(
                    _score_row(
                        year=2026,
                        province="湖南省",
                        subject_category="历史类",
                        score_type="控制线",
                        score=hist,
                        admission_rank=None,
                        batch=batch,
                        source_file=source_file,
                    )
                )
            if phys is not None:
                score_rows.append(
                    _score_row(
                        year=2026,
                        province="湖南省",
                        subject_category="物理类",
                        score_type="控制线",
                        score=phys,
                        admission_rank=None,
                        batch=batch,
                        source_file=source_file,
                    )
                )
    return score_rows, []


def _parse_summary_2026_score(
    content: str,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    """2026 投档线表（组粒度）：列 = 科类0/专业组号1/专业名称2/计划数3/最高分4/最低投档分5。"""
    _, rows = parse_pipe_table(content)
    if not rows:
        return [], []

    filled = forward_fill(rows, {0})
    score_rows: list[dict] = []
    plan_rows: list[dict] = []

    for row in filled:
        subject = normalize_subject(strip_markdown_bold(row[0]))
        group_no = normalize_group(strip_markdown_bold(row[1]), subject)
        if not subject or not group_no:
            continue

        plan = _parse_int(row[3])
        if plan is not None:
            plan_rows.append(
                _plan_row(
                    year=2026,
                    province="湖南省",
                    subject_category=subject,
                    plan=plan,
                    group_no=group_no,
                    major=None,
                    source_file=source_file,
                )
            )

        max_score, max_rank = parse_score_rank(row[4])
        if max_score is not None:
            score_rows.append(
                _score_row(
                    year=2026,
                    province="湖南省",
                    subject_category=subject,
                    score_type="最高分",
                    score=max_score,
                    admission_rank=max_rank,
                    group_no=group_no,
                    major=None,
                    source_file=source_file,
                )
            )

        min_score, min_rank = parse_score_rank(row[5])
        if min_score is not None:
            score_rows.append(
                _score_row(
                    year=2026,
                    province="湖南省",
                    subject_category=subject,
                    score_type="最低分",
                    score=min_score,
                    admission_rank=min_rank,
                    group_no=group_no,
                    major=None,
                    source_file=source_file,
                )
            )

    return score_rows, plan_rows


def parse_summary(text: str, source_file: str) -> tuple[list[dict], list[dict]]:
    score_rows: list[dict] = []
    plan_rows: list[dict] = []

    for title, content in _split_headings(text):
        if "2024年省内" in title:
            s, p = _parse_summary_province(content, 2024, "湖南省", source_file)
        elif "2025年湖南省" in title:
            s, p = _parse_summary_province(content, 2025, "湖南省", source_file)
        elif "2025年省外" in title:
            s, p = _parse_summary_outprovince(content, source_file)
        elif "控制分数线" in title:
            s, p = _parse_control_lines(content, source_file)
        elif "投档分数线" in title or "投档分" in title:
            s, p = _parse_summary_2026_score(content, source_file)
        else:
            continue
        score_rows.extend(s)
        plan_rows.extend(p)

    return score_rows, plan_rows


# ---------------------------------------------------------------------------
# 文件4：长沙工业学院2024年拟招生本科专业及人数.md
# ---------------------------------------------------------------------------
def parse_plan_2024(text: str, source_file: str) -> tuple[list[dict], list[dict]]:
    _, rows = parse_pipe_table(text)
    plan_rows: list[dict] = []

    for row in rows:
        if len(row) < 8:
            continue
        seq = strip_markdown_bold(row[0])
        major = normalize_major(strip_markdown_bold(row[2]))
        if not major or seq in {"合计", "序号"}:
            continue

        major_code = strip_markdown_bold(row[1]) or None
        tuition = _parse_int(row[6])
        requirement = strip_markdown_bold(row[7]) or None
        hist = _parse_int(row[4])
        phys = _parse_int(row[5])
        total = _parse_int(row[3])

        if hist is not None:
            plan_rows.append(
                _plan_row(
                    year=2024,
                    province="湖南省",
                    subject_category="历史类",
                    plan=hist,
                    major=major,
                    tuition=tuition,
                    major_code=major_code,
                    subject_requirement=requirement,
                    source_file=source_file,
                )
            )
        if phys is not None:
            plan_rows.append(
                _plan_row(
                    year=2024,
                    province="湖南省",
                    subject_category="物理类",
                    plan=phys,
                    major=major,
                    tuition=tuition,
                    major_code=major_code,
                    subject_requirement=requirement,
                    source_file=source_file,
                )
            )
        if hist is None and phys is None and total is not None:
            plan_rows.append(
                _plan_row(
                    year=2024,
                    province="湖南省",
                    subject_category="艺术类",
                    plan=total,
                    major=major,
                    tuition=tuition,
                    major_code=major_code,
                    subject_requirement=requirement,
                    source_file=source_file,
                )
            )

    return [], plan_rows


# ---------------------------------------------------------------------------
# 文件5/7 省内分节 + 文件6/7 外省交叉表
# ---------------------------------------------------------------------------
def _parse_sectioned_plan(
    title: str,
    content: str,
    year: int,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    """省内分节招生计划：节头元信息 + 组行/专业行表格。"""
    meta = parse_section_metadata(content)
    subject = normalize_subject(meta.get("科类", "")) or normalize_subject(title)
    batch = meta.get("批次") or None
    _, rows = parse_pipe_table(content)
    plan_rows: list[dict] = []

    current_group: str | None = None
    for row in rows:
        if len(row) < 2:
            continue
        cell0 = strip_markdown_bold(row[0])
        cell1 = strip_markdown_bold(row[1])
        if not cell0 or not cell1:
            continue
        if "长沙工业学院" in cell1 or "院校" in cell1:
            continue
        if "组" in cell1:
            current_group = normalize_group(cell1, subject)
            plan = _parse_int(row[3])
            if plan is not None:
                plan_rows.append(
                    _plan_row(
                        year=year,
                        province="湖南省",
                        subject_category=subject or "",
                        plan=plan,
                        group_no=current_group,
                        major=None,
                        batch=batch,
                        source_file=source_file,
                    )
                )
        elif cell0.isdigit():
            major = normalize_major(cell1)
            if not major:
                continue
            duration = _parse_int(row[2])
            plan = _parse_int(row[3])
            tuition = _parse_int(row[4])
            if plan is None:
                continue
            plan_rows.append(
                _plan_row(
                    year=year,
                    province="湖南省",
                    subject_category=subject or "",
                    plan=plan,
                    group_no=current_group,
                    major=major,
                    tuition=tuition,
                    duration=duration,
                    batch=batch,
                    source_file=source_file,
                )
            )

    return [], plan_rows


def _parse_cross_plan_table(
    content: str,
    year: int,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    """外省交叉表：科类由 ⊕文史/理工合计 分隔行决定。"""
    header, rows = parse_pipe_table(content)
    if not header:
        return [], []

    plan_rows: list[dict] = []
    triples = transpose_cross_table(header, rows)

    # 科类状态机：重新按行序判定专业行的科类
    current_subject = "历史类"
    subject_by_major: dict[str, str] = {}
    for row in rows:
        if not row:
            continue
        cell0 = strip_markdown_bold(row[0])
        if "文史" in cell0 or "历史" in cell0:
            current_subject = "物理类"
            continue
        if "理工" in cell0 or "物理" in cell0:
            current_subject = ""
            continue
        if any(k in cell0 for k in ("合计", "总计", "★", "△", "⊕")):
            continue
        if cell0:
            subject_by_major[cell0] = current_subject

    for major_raw, province, plan in triples:
        subject = subject_by_major.get(major_raw, "")
        plan_rows.append(
            _plan_row(
                year=year,
                province=province,
                subject_category=subject,
                plan=plan,
                major=normalize_major(major_raw),
                source_file=source_file,
            )
        )

    return [], plan_rows


def parse_hunan_plan_2025(text: str, source_file: str) -> tuple[list[dict], list[dict]]:
    score_rows: list[dict] = []
    plan_rows: list[dict] = []
    for title, content in _split_headings(text):
        s, p = _parse_sectioned_plan(title, content, 2025, source_file)
        score_rows.extend(s)
        plan_rows.extend(p)
    return score_rows, plan_rows


def parse_outprovince_plan_2025(
    text: str,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    return _parse_cross_plan_table(text, 2025, source_file)


def parse_plan_2026(text: str, source_file: str) -> tuple[list[dict], list[dict]]:
    score_rows: list[dict] = []
    plan_rows: list[dict] = []
    for title, content in _split_headings(text):
        if "外省" in title:
            s, p = _parse_cross_plan_table(content, 2026, source_file)
        else:
            s, p = _parse_sectioned_plan(title, content, 2026, source_file)
        score_rows.extend(s)
        plan_rows.extend(p)
    return score_rows, plan_rows


# ---------------------------------------------------------------------------
# 注册表 + 统一入口
# ---------------------------------------------------------------------------
PARSE_REGISTRY = {
    "CIT2425省内投档线.md": parse_cit2425,
    "CIT2026省内投档线.md": parse_cit2026,
    "长沙工业学院历年录取分数线汇总.md": parse_summary,
    "长沙工业学院2024年拟招生本科专业及人数.md": parse_plan_2024,
    "长沙工业学院2025年湖南省招生计划.md": parse_hunan_plan_2025,
    "长沙工业学院2025年外省分专业计划.md": parse_outprovince_plan_2025,
    "长沙工业学院2026年招生计划.md": parse_plan_2026,
}


def parse_all(raw_dir: Path) -> tuple[list[dict], list[dict]]:
    """解析 raw_dir 下所有已注册的结构化文件。"""
    score_rows: list[dict] = []
    plan_rows: list[dict] = []

    for filename, parser in PARSE_REGISTRY.items():
        file_path = raw_dir / filename
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8")
        source_file = f"{RAW_PREFIX}{filename}"
        s, p = parser(text, source_file)
        score_rows.extend(s)
        plan_rows.extend(p)

    return score_rows, plan_rows
