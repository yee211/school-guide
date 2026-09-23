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

# 口语缩写/常用简称 → 规范专业全名（与库中 major 字段一致）。
# 一个缩写可对应多个专业（如「电子信息」），由 SQL 的 ANY 匹配兜底后交由 LLM 呈现。
MAJOR_ALIASES: dict[str, tuple[str, ...]] = {
    "机械设计制造": ("机械设计制造及其自动化",),
    "机械设计": ("机械设计制造及其自动化",),
    "机械制造": ("机械设计制造及其自动化",),
    "数据科学": ("数据科学与大数据技术",),
    "大数据技术": ("数据科学与大数据技术",),
    "大数据管理": ("大数据管理与应用",),
    "大数据": ("数据科学与大数据技术", "大数据管理与应用"),
    "电子信息": ("电子信息工程", "电子信息科学与技术"),
    "计算机": ("计算机科学与技术",),
    "计科": ("计算机科学与技术",),
    "软件": ("软件工程",),
    "视觉传达": ("视觉传达设计",),
    "视传": ("视觉传达设计",),
    "数字媒体": ("数字媒体技术",),
    "数媒": ("数字媒体技术",),
    "智能科学": ("智能科学与技术",),
    "智能制造": ("智能制造工程",),
    "机器人": ("机器人工程",),
    "新能源汽车": ("新能源汽车工程",),
    "新能源": ("新能源汽车工程",),
    "虚拟现实": ("虚拟现实技术",),
    "人文地理": ("人文地理与城乡规划",),
    "城乡规划": ("人文地理与城乡规划",),
    "数学": ("数学与应用数学（师范类）",),
    "应用数学": ("数学与应用数学（师范类）",),
    "艺术设计": ("艺术设计学",),
    "会计": ("会计学",),
    "金融": ("金融学",),
    "电商": ("电子商务",),
    "网工": ("网络工程",),
}

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


def _alias_matched_majors(text: str, full_name_hits: list[str]) -> list[str]:
    """把口语缩写（视传/计科/大数据等）映射为规范专业全名。

    长缩写优先：若短缩写是某个已命中的更长缩写或专业全名的子串则跳过，
    避免「电子信息工程分数线」误带出「电子信息科学与技术」。
    """
    lowered = text.lower()
    matched_aliases = [
        alias
        for alias in sorted(MAJOR_ALIASES, key=len, reverse=True)
        if alias in text or alias.lower() in lowered
    ]
    majors: list[str] = []
    for alias in matched_aliases:
        if any(
            alias != other and alias in other
            for other in (*matched_aliases, *full_name_hits)
        ):
            continue
        majors.extend(MAJOR_ALIASES[alias])
    return majors


def _extract_majors(text: str) -> list[str]:
    full_name_hits = [
        _canonical_major(major) for major in KNOWN_MAJORS if major in text
    ]
    return _ordered_unique(
        [*full_name_hits, *_alias_matched_majors(text, full_name_hits)]
    )


# 新闻类正文里经常出现「录取分数线」「招生计划」等词，如果先走关键词匹配，
# 这些 chunk 会被误标成数据类文档，进而被数据型查询召回——但它们并不包含
# 真实数据，只会给生成模型喂噪声。所以类目判定必须排在关键词判定之前。
# 类目名的来源：合并语料每个文件以「# <类目>」开头，splitter 的
# _heading_context 会把生效的标题层级回填进每个 chunk 正文。
_NEWS_CATEGORIES = (
    "综合新闻",
    "学院要闻",
    "新闻",
    "视觉长工",
    "媒体长工",
)

_OVERVIEW_CATEGORIES = (
    "学校概况",
    "学校简介",
    "师资队伍",
    "教学机构",
    "科学研究",
    "党政管理机构",
    "党建思政",
    "校友工作",
)


def _classify_document_type(text: str) -> str:
    lowered = text.lower()
    if any(f"# {category}" in text for category in _NEWS_CATEGORIES):
        return "校园动态"
    if any(f"# {category}" in text for category in _OVERVIEW_CATEGORIES):
        return "学校概况"
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
    elif (
        any(
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
        )
        and "转专业" not in query
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
