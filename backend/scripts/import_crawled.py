"""把爬虫产出的校园官网语料筛选、按类目合并，落盘到 data/raw/crawled/。

只做筛选与落盘，不触碰向量索引、不调用 embedding。
默认 dry-run，确认统计无误后加 --apply 才真正写文件。

用法：
    python -m scripts.import_crawled                 # 只看统计
    python -m scripts.import_crawled --apply         # 落盘
    python -m scripts.import_crawled --src D:/path/to/climb/output --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TARGET_DIR = BACKEND_DIR / "data" / "raw" / "crawled"
DEFAULT_SRC = Path(r"D:/projects/py/climb/output")

# 对校园问答零价值，或体量大到会主导检索的类目，直接不入库。
EXCLUDED_CATEGORIES = {
    "招标采购",
    "中标公告",
    "流标公告",
    "废标公告",
    "首页顶部轮换图",
    "测试栏目",
    "默认分类",
    "通讯员投稿系统",
    # 单类 193 万字符、占全库 65%，且为外部媒体转载，重复度高。
    "媒体长工",
    # 时效性校园新闻。本系统面向尚未入学的考生，问的是"多少分能上、
    # 有哪些专业"，新闻既答不上又会挤占检索名额。
    "综合新闻",
    "学院要闻",
    "新闻",
    "视觉长工",
}

# 正文（去头、去图、去标记后）少于此字数的文档视为图片型空壳，不入库。
MIN_BODY_CHARS = 200

_HEADER_FIELD = re.compile(r"^-\s+\*\*(.+?)\*\*:\s*(.*)$")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_BARE_URL = re.compile(r"(?:https?:)?//\S+")
_MD_NOISE = re.compile(r"[#>*|\[\]()]")


def _parse_article(path: Path) -> tuple[dict[str, str], str, str]:
    """拆出爬虫写入的元数据头、标题和正文。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()

    title = ""
    header: dict[str, str] = {}
    body_start = 0

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
            continue
        matched = _HEADER_FIELD.match(stripped)
        if matched:
            header[matched.group(1)] = matched.group(2).strip()
            continue
        if stripped == "---":
            body_start = index + 1
            break

    body = "\n".join(lines[body_start:])
    return header, title, body


def _clean_body(body: str) -> str:
    """去掉图片链接、裸 URL 和多余空行，正文文本保持原样。"""
    text = _IMAGE.sub(" ", body)
    text = _BARE_URL.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _body_char_count(text: str) -> int:
    """估算真实正文字数：剥掉 markdown 标记后计数，用于筛掉图片型空壳。"""
    return len(_MD_NOISE.sub("", re.sub(r"\s+", "", text)))


def collect(src: Path) -> tuple[list[dict], list[dict], Counter]:
    jsonl = src / "articles.jsonl"
    if not jsonl.exists():
        raise SystemExit(f"找不到 {jsonl}")

    kept: list[dict] = []
    image_only: list[dict] = []
    skipped = Counter()

    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped["JSON解析失败"] += 1
            continue

        saved_markdown = record.get("saved_markdown")
        if not saved_markdown:
            skipped["缺少saved_markdown"] += 1
            continue

        category = record.get("category", "")

        if category in EXCLUDED_CATEGORIES:
            skipped[f"类目排除·{category}"] += 1
            continue

        path = src / saved_markdown
        if not path.exists():
            skipped["文件缺失"] += 1
            continue

        header, title, body = _parse_article(path)
        cleaned = _clean_body(body)
        char_count = _body_char_count(cleaned)

        if char_count < MIN_BODY_CHARS:
            image_only.append(
                {
                    "id": record.get("id"),
                    "category": category,
                    "title": title or record.get("title", ""),
                    "url": record.get("url", ""),
                    "publish_date": record.get("publish_date", ""),
                    "body_chars": char_count,
                    "image_count": len(_IMAGE.findall(body)),
                    "saved_markdown": record["saved_markdown"],
                }
            )
            skipped["图片型空壳"] += 1
            continue

        kept.append(
            {
                "category": category,
                "title": title or record.get("title", ""),
                "url": record.get("url", ""),
                "publish_date": record.get("publish_date", "")
                or header.get("发布时间", ""),
                "source": header.get("信息来源", "")
                or record.get("source", ""),
                "views": record.get("views", 0),
                "body": cleaned,
                "chars": char_count,
            }
        )

    return kept, image_only, skipped


def render_category(category: str, articles: list[dict]) -> str:
    """把一个类目下的文章合并成单个 markdown，每篇一个 ## 小节。"""
    # 新的在前，同类目内按发布时间倒序。
    ordered = sorted(
        articles,
        key=lambda a: a["publish_date"] or "",
        reverse=True,
    )
    parts = [f"# {category}\n"]
    # 单篇且标题与类目同名（22 个专业单页都是这种）时不再写 ## 标题，否则
    # splitter 的 _heading_context 会把标题栈回填一遍，chunk 开头出现三次
    # 同一个标题，白占 token。
    lone_duplicate = len(ordered) == 1 and ordered[0]["title"] == category
    for article in ordered:
        meta_line = " · ".join(
            value
            for value in (article["source"], article["publish_date"])
            if value
        )
        heading = "" if lone_duplicate else f"## {article['title']}\n"
        parts.append(f"{heading}> {meta_line}\n\n{article['body']}\n")
    return "\n".join(parts)


def safe_filename(category: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", category).strip() or "未分类"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=os.getenv("CRAWL_OUTPUT", str(DEFAULT_SRC)))
    parser.add_argument("--apply", action="store_true", help="真正写文件（默认 dry-run）")
    args = parser.parse_args()

    src = Path(args.src)
    kept, image_only, skipped = collect(src)

    by_category: dict[str, list[dict]] = defaultdict(list)
    for article in kept:
        by_category[article["category"]].append(article)

    print(f"数据源：{src}")
    print(f"入选 {len(kept)} 篇 / {sum(a['chars'] for a in kept):,} 字，"
          f"合并为 {len(by_category)} 个类目文档\n")

    print(f"{'类目':<14}{'篇':>5}{'字数':>10}{'≈chunk':>8}")
    print("-" * 40)
    for category, articles in sorted(
        by_category.items(), key=lambda kv: -sum(a["chars"] for a in kv[1])
    ):
        chars = sum(a["chars"] for a in articles)
        print(f"{category[:14]:<14}{len(articles):>5}{chars:>10,}{chars // 420:>8}")

    print("\n排除统计：")
    for reason, count in skipped.most_common():
        print(f"  {reason:<24}{count:>5}")

    if image_only:
        print(f"\n正文不足 {MIN_BODY_CHARS} 字、内容全在图片里的文档 "
              f"{len(image_only)} 篇，本次不入库，前 10 条：")
        for item in sorted(image_only, key=lambda x: -x["image_count"])[:10]:
            print(f"  [{item['category'][:8]:<9}] 图{item['image_count']:>3}张 "
                  f"正文{item['body_chars']:>4}字  {item['title'][:40]}")

    if not args.apply:
        print("\n（dry-run，未写任何文件。确认无误后加 --apply）")
        return

    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True)

    manifest: dict[str, list[dict]] = {}
    for category, articles in by_category.items():
        filename = f"{safe_filename(category)}.md"
        (TARGET_DIR / filename).write_text(
            render_category(category, articles), encoding="utf-8"
        )
        # URL 等引用信息不进正文，避免污染 embedding，改由 manifest 提供。
        manifest[filename] = [
            {
                "title": a["title"],
                "url": a["url"],
                "publish_date": a["publish_date"],
                "source": a["source"],
                "views": a["views"],
                "chars": a["chars"],
            }
            for a in sorted(
                articles, key=lambda x: x["publish_date"] or "", reverse=True
            )
        ]

    (TARGET_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (TARGET_DIR / "_image_only.json").write_text(
        json.dumps(image_only, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    written = sum(1 for _ in TARGET_DIR.glob("*.md"))
    print(f"\n已写入 {TARGET_DIR}")
    print(f"  {written} 个类目文档 + _manifest.json + _image_only.json")


if __name__ == "__main__":
    main()
