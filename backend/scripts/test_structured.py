"""结构化数据落库 + 精确查询的验证脚本（需 PostgreSQL 就绪）。"""

from app.rag.loader import RAW_DATA_DIR
from app.rag.metadata import infer_retrieval_filters
from app.structured.normalize import (
    normalize_group,
    normalize_major,
    normalize_subject,
    parse_score_rank,
)
from app.structured.parsers import parse_all
from app.structured.query import structured_query_service


def main() -> None:
    # 1. 数值解析
    assert parse_score_rank("465 (132431)") == (465.0, 132431)
    assert parse_score_rank("515分（位次86215）") == (515.0, 86215)
    assert parse_score_rank("279.9") == (279.9, None)
    assert parse_score_rank("/") == (None, None)

    # 2. 归一化
    assert normalize_subject("普通类(首选物理)") == "物理类"
    assert normalize_subject("理工（物理）") == "物理类"
    assert normalize_subject("文史（历史）") == "历史类"
    assert normalize_major("数学与应用数学(师范类)") == "数学与应用数学（师范类）"
    assert normalize_group("第103组", "物理类") == "物理103组"
    assert normalize_group("物理105组", None) == "物理105组"

    # 3. 解析行数
    score_rows, plan_rows = parse_all(RAW_DATA_DIR)
    assert len(score_rows) > 0
    assert len(plan_rows) > 0

    # 4. 冲突保留：2026 物理103组 最低分，文件2 的 480 与文件3 的 472 并存
    conflict = {
        r["score"]
        for r in score_rows
        if r["year"] == 2026
        and r["group_no"] == "物理103组"
        and r["score_type"] == "最低分"
    }
    assert 480.0 in conflict and 472.0 in conflict, conflict

    # 5. 结构化查询：2026 物理105组 最低投档分命中 499
    catalog = structured_query_service.get_catalog()
    assert catalog.years and catalog.majors and catalog.groups

    question = "2026年物理105组最低投档分是多少？"
    filters = infer_retrieval_filters(question, catalog)
    assert filters.groups == ("物理105组",), filters.as_dict()
    assert filters.document_types == ("录取分数",)

    result = structured_query_service.query(filters, "最低分")
    assert result.is_targeted
    assert any(r["score"] == 499.0 for r in result.score_rows), result.score_rows

    # 6. 招生计划查询：人工智能学费 4800
    question = "人工智能专业学费是多少？"
    filters = infer_retrieval_filters(question, catalog)
    assert filters.document_types == ("招生计划",), filters.as_dict()
    result = structured_query_service.query(filters)
    assert any(r["tuition"] == 4800.0 for r in result.plan_rows), result.plan_rows

    print(
        {
            "score_rows": len(score_rows),
            "plan_rows": len(plan_rows),
            "conflict_103组": sorted(conflict),
            "catalog_years": catalog.years,
            "catalog_majors_count": len(catalog.majors),
            "catalog_groups_count": len(catalog.groups),
        }
    )
    print("test_structured 全部通过")


if __name__ == "__main__":
    main()
