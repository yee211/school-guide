"""把 7 个结构化 Markdown 文件解析并全量写入 PostgreSQL。"""

from app.rag.loader import RAW_DATA_DIR
from app.structured.parsers import parse_all
from app.structured.store import reload


def main() -> None:
    print("开始解析结构化招生/录取数据……")
    score_rows, plan_rows = parse_all(RAW_DATA_DIR)

    print(f"解析到 {len(score_rows)} 条分数记录、{len(plan_rows)} 条计划记录")

    score_count, plan_count = reload(score_rows, plan_rows)

    print(f"成功写入 {score_count} 条分数、{plan_count} 条计划")
    print("结构化数据入库完成")


if __name__ == "__main__":
    main()
