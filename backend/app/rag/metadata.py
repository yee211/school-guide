from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_core.documents import Document


YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")

GROUP_PATTERN = re.compile(r"(?:(物理|历史|艺术))?(\d{3})(?:专业)?组")

_SUBJECT_PREFIX = {"物理类": "物理", "历史类": "历史", "艺术类": "艺术"}

KNOWN_MAJORS = (
    "机械设计制造及其自动化",
    "数据科学与大数据技术",
    "电子信息科学与技术",
    "数学与应用数学（师范类）",
    "数学与应用数学(师范类)",
    "人文地理与城乡规划",
    "大数据管理与应用",
    "新能源汽车工程",
    "计算机科学与技术",
    "视觉传达设计",
    "数字媒体技术",
    "智能科学与技术",
    "电子信息工程",
    "数学与应用数学",
    "虚拟现实技术",
    "智能制造工程",
    "机器人工程",
    "艺术设计学",
    "通信工程",
    "网络工程",
    "软件工程",
    "人工智能",
    "电子商务",
    "会计学",
    "金融学",
)

PROVINCE_ALIASES = {
    "北京": "北京市",
    "天津": "天津市",
    "河北": "河北省",
    "山西": "山西省",
    "内蒙古": "内蒙古自治区",
    "辽宁": "辽宁省",
    "吉林": "吉林省",
    "黑龙江": "黑龙江省",
    "上海": "上海市",
    "江苏": "江苏省",
    "浙江": "浙江省",
    "安徽": "安徽省",
    "福建": "福建省",
    "江西": "江西省",
    "山东": "山东省",
    "河南": "河南省",
    "湖北": "湖北省",
    "湖南": "湖南省",
    "广东": "广东省",
    "广西": "广西壮族自治区",
    "海南": "海南省",
    "重庆": "重庆市",
    "四川": "四川省",
    "贵州": "贵州省",
    "云南": "云南省",
    "西藏": "西藏自治区",
    "陕西": "陕西省",
    "甘肃": "甘肃省",
    "青海": "青海省",
    "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区",
    "澳门": "澳门特别行政区",
    "台湾": "台湾省",
}

SUBJECT_ALIASES = {
    "物理类": ("物理类", "首选物理", "理工（物理）", "理工(物理)"),
    "历史类": ("历史类", "首选历史", "文史（历史）", "文史(历史)"),
    "艺术类": ("艺术类", "美术与设计类"),
}


@dataclass(frozen=True, slots=True)
class FilterCatalog:
    years: tuple[str, ...] = ()
    subject_categories: tuple[str, ...] = ()
    provinces: tuple[str, ...] = ()
    majors: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalFilters:
    years: tuple[str, ...] = ()
    subject_categories: tuple[str, ...] = ()
    provinces: tuple[str, ...] = ()
    majors: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.years,
                self.subject_categories,
                self.provinces,
                self.majors,
                self.document_types,
            )
        )

    def as_dict(self) -> dict[str, list[str]]:
        return {
            key: list(value)
            for key, value in (
                ("years", self.years),
                ("subject_categories", self.subject_categories),
                ("provinces", self.provinces),
                ("majors", self.majors),
                ("document_types", self.document_types),
                ("groups", self.groups),
            )
            if value
        }


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _extract_years(text: str) -> list[str]:
    return sorted(set(YEAR_PATTERN.findall(text)))


def _extract_groups(text: str) -> list[str]:
    """抽取专业组，如 物理105组 / 105组（前缀缺失时保留裸编号）。"""
    groups: list[str] = []
    for match in GROUP_PATTERN.finditer(text):
        prefix = match.group(1)
        num = match.group(2)
        groups.append(f"{prefix}{num}组" if prefix else f"{num}组")
    return _ordered_unique(groups)


def _extract_subject_categories(text: str) -> list[str]:
    return [
        category
        for category, aliases in SUBJECT_ALIASES.items()
        if any(alias in text for alias in aliases)
    ]


def _extract_provinces(text: str) -> list[str]:
    provinces = [
        canonical
        for alias, canonical in PROVINCE_ALIASES.items()
        if alias in text
    ]
    return _ordered_unique(provinces)


def _canonical_major(major: str) -> str:
    return major.replace("(师范类)", "（师范类）")


def _extract_majors(text: str) -> list[str]:
    return _ordered_unique(
        [
            _canonical_major(major)
            for major in KNOWN_MAJORS
            if major in text
        ]
    )


def _classify_document_type(text: str) -> str:
    lowered = text.lower()
    if any(keyword in text for keyword in ("投档", "录取分数", "分数线")):
        return "录取分数"
    if any(keyword in text for keyword in ("招生计划", "拟招生", "专业计划")):
        return "招生计划"
    if "图书馆" in text or "library" in lowered:
        return "图书馆"
    if any(
        keyword in text
        for keyword in (
            "宿舍",
            "食堂",
            "校园跑",
            "快递站",
            "军训",
            "到校路线",
        )
    ):
        return "校园生活"
    if "school_overview" in lowered or "学校概况" in text:
        return "学校概况"
    return "其他"


def enrich_document_metadata(document: Document) -> Document:
    metadata = dict(document.metadata)
    source_context = " ".join(
        str(metadata.get(key, ""))
        for key in ("source", "filename", "title")
    )
    full_context = f"{source_context}\n{document.page_content}"

    years = _extract_years(full_context)
    subject_categories = _extract_subject_categories(full_context)
    provinces = _extract_provinces(full_context)
    if "省内" in source_context and "湖南省" not in provinces:
        provinces.append("湖南省")
    majors = _extract_majors(full_context)
    document_type = _classify_document_type(full_context)
    if (
        not provinces
        and subject_categories
        and document_type in {"录取分数", "招生计划"}
        and "外省" not in full_context
    ):
        provinces.append("湖南省")

    metadata.update(
        {
            "years": years,
            "subject_categories": subject_categories,
            "provinces": provinces,
            "majors": majors,
            "document_type": document_type,
        }
    )
    for singular, values in (
        ("year", years),
        ("subject_category", subject_categories),
        ("province", provinces),
        ("major", majors),
    ):
        if len(values) == 1:
            metadata[singular] = values[0]
        else:
            metadata.pop(singular, None)

    return Document(
        page_content=document.page_content,
        metadata=metadata,
    )


def infer_retrieval_filters(
    query: str,
    catalog: FilterCatalog,
) -> RetrievalFilters:
    # 显式条件即使当前库中没有，也必须保留。这样查询不存在的年份、
    # 省份或专业会返回空结果，不会静默退化成不加过滤的错误答案。
    years = tuple(_extract_years(query))

    document_types: tuple[str, ...] = ()
    if any(
        keyword in query
        for keyword in (
            "投档",
            "录取分",
            "录取线",
            "分数线",
            "最低分",
            "最高分",
            "位次",
        )
    ):
        document_types = ("录取分数",)
    elif any(
        keyword in query
        for keyword in (
            "招生计划",
            "计划数",
            "招生人数",
            "招生多少",
            "招多少",
            "学费",
            "收费",
            "学制",
            "选科",
            "选考",
        )
    ):
        document_types = ("招生计划",)
    elif any(
        keyword in query
        for keyword in ("图书馆", "借阅", "借书", "还书", "馆藏")
    ):
        document_types = ("图书馆",)
    elif any(
        keyword in query
        for keyword in ("宿舍", "食堂", "校园跑", "快递", "军训", "交通")
    ):
        document_types = ("校园生活",)

    admission_query = bool(
        set(document_types) & {"录取分数", "招生计划"}
    )
    inferred_subjects = _extract_subject_categories(query)
    if admission_query:
        for keyword, category in (
            ("物理", "物理类"),
            ("历史", "历史类"),
            ("艺术", "艺术类"),
            ("美术", "艺术类"),
        ):
            if keyword in query and category not in inferred_subjects:
                inferred_subjects.append(category)
    subject_categories = tuple(inferred_subjects)

    inferred_provinces = _extract_provinces(query)
    if (
        admission_query
        and "省内" in query
        and "湖南省" not in inferred_provinces
    ):
        inferred_provinces.append("湖南省")
    provinces = tuple(inferred_provinces)
    majors = tuple(
        _ordered_unique(
            [
                *_extract_majors(query),
                *(
                    major
                    for major in sorted(
                        catalog.majors,
                        key=len,
                        reverse=True,
                    )
                    if major in query
                ),
            ]
        )
    )

    raw_groups = _extract_groups(query)
    groups_list: list[str] = []
    for group in raw_groups:
        if group[0].isdigit() and len(subject_categories) == 1:
            prefix = _SUBJECT_PREFIX.get(subject_categories[0])
            groups_list.append(f"{prefix}{group}" if prefix else group)
        else:
            groups_list.append(group)
    groups = tuple(_ordered_unique(groups_list))

    return RetrievalFilters(
        years=years,
        subject_categories=subject_categories,
        provinces=provinces,
        majors=majors,
        document_types=document_types,
        groups=groups,
    )
