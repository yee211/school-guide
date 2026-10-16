"""Explicit answer checklist and grounded coverage validation."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from itertools import product

from pydantic import BaseModel, Field
from app.rag.metadata import FilterCatalog, infer_retrieval_filters

METRICS = (
    ("学费", r"学费|收费标准", "tuition"),
    ("招生人数", r"招生人数|招生多少|招多少|计划数|招生计划", "plan"),
    ("录取分数", r"分数线|录取分|投档线|最低分|最高分|多少分", "score"),
    ("位次", r"位次|排名", "admission_rank"),
    ("选科要求", r"选科|科目要求|科目限制", "subject_requirement"),
    ("学制", r"学制|读几年", "duration"),
    ("专业特色", r"特色|优势", None),
    ("就业方向", r"就业|职业方向", None),
    ("课程设置", r"课程|培养方案", None),
    ("校园设施", r"校园设施|校园环境", None),
    ("食堂位置", r"食堂|餐厅", None),
    ("快递站位置", r"快递|驿站", None),
    ("住宿条件", r"宿舍|住宿", None),
)


def normalize_years(query):
    year = datetime.now(timezone(timedelta(hours=8))).year
    for word, value in (("今年", year), ("去年", year-1), ("明年", year+1)):
        query = query.replace(word, f"{value}年")
    return query


@dataclass(frozen=True)
class Clarification:
    answer: str


def admission_clarification(query):
    if re.search(r"复读|专升本|报考资格|报名条件", query) and not re.search(r"\d+\s*分|分数线|投档线|录取分", query):
        return None
    # Broad/historical listings are intentional; only narrow score questions need all conditions.
    if not re.search(r"能上|能报|够不够|录取机会|多少分|分数线|投档线|录取分", query):
        return None
    if re.search(r"历年|近几年|各省|全国|各科|汇总|趋势|有哪些|什么意思|是什么|政策", query):
        return None
    filters = infer_retrieval_filters(normalize_years(query), FilterCatalog())
    missing = []
    if not filters.years:
        missing.append("招生年份")
    if not filters.provinces:
        missing.append("生源省份")
    if not filters.subject_categories:
        missing.append("科类或选科（例如物理类、历史类）")
    aggregate = bool(re.search(r"各(?:个)?专业组|所有专业组|全部专业组|各专业|所有专业|全部专业|各组", query))
    personalized = bool(re.search(r"能上|能报|够不够|录取机会", query))
    # With year/province/category supplied, a school-level score overview is valid.
    if personalized and not aggregate and not filters.majors and not filters.groups:
        missing.append("专业或专业组")
    if not missing:
        return None
    return Clarification("为了查询对应的录取数据，请补充" + "、".join(missing) + "。已经提供的条件不用重复。历年分数只能作为参考，不能保证录取。")


@dataclass(frozen=True)
class Requirement:
    id: str
    label: str
    query: str
    tool: str
    field: str | None
    major: str
    years: tuple[str, ...]
    provinces: tuple[str, ...]
    subjects: tuple[str, ...]
    groups: tuple[str, ...] = ()
    scope_resolved: bool = True

    def accepts(self, evidence):
        if not self.scope_resolved:
            return False
        if self.field:
            row = evidence.facts
            if not row or row.get(self.field) is None or row.get(self.field) == "":
                return False
            if self.major and row.get("major") != self.major:
                return False
            if self.groups:
                group = str(row.get("group_no") or "")
                if not any(group == requested or (requested.isdigit() and group.endswith(requested)) for requested in self.groups):
                    return False
            for values, key in ((self.years, "year"), (self.provinces, "province"), (self.subjects, "subject_category")):
                if values and str(row.get(key)) not in values:
                    return False
        elif self.major:
            if self.major not in evidence.content:
                return False
        return True


def build_requirements(query, catalog=None, *, catalog_unavailable=False):
    query = normalize_years(query)
    filters = infer_retrieval_filters(query, catalog or FilterCatalog())
    aggregate = bool(re.search(r"各专业|所有专业|全部专业|各组|各专业组|所有专业组|全部专业组", query))
    unresolved = not filters.majors and not filters.groups and not aggregate and (
        catalog_unavailable or ("专业" in query and query.strip() not in ("专业特色", "专业优势", "专业就业方向", "专业课程"))
    )
    metrics = [m for m in METRICS if re.search(m[1], query)]
    majors = filters.majors or ("",)
    result = []
    for major in majors:
        for label, _, field in metrics:
            conditions = product(filters.years or ("",), filters.provinces or ("",), filters.subject_categories or ("",), filters.groups or ("",)) if field else [("", "", "", "")]
            for year, province, subject, group in conditions:
                context = " ".join(v for v in (year, province, subject, group) if v)
                result.append(Requirement(
                    f"r{len(result)+1}", f"{context + ' ' if context else ''}{major or '学校'}：{label}",
                    (query if unresolved else f"{context} {major or '长沙工业学院'} {label}".strip()),
                    "query_admission_data" if field else "search_school_knowledge",
                    field, major, (year,) if year else (), (province,) if province else (),
                    (subject,) if subject else (), (group,) if group else (), not unresolved,
                ))
                if len(result) >= 20:
                    return result
    return result


class CoverageItem(BaseModel):
    requirement_id: str
    status: Literal["supported", "missing", "conflict"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class CoverageReport(BaseModel):
    items: list[CoverageItem] = Field(default_factory=list, max_length=20)


def validate_coverage(requirements, evidence, report):
    output = {r.id: "missing" for r in requirements}
    by_id = {r.id: r for r in requirements}
    for item in report.items:
        req = by_id.get(item.requirement_id)
        if not req or item.status == "missing":
            continue
        refs = list(dict.fromkeys(item.evidence_ids))
        if refs and all(key in evidence and req.accepts(evidence[key]) for key in refs):
            if item.status == "supported" or len(refs) >= 2:
                output[req.id] = item.status
    return output
