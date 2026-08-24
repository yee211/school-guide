"""数据清洗模块（DocumentCleaner）单元测试。"""
import io
import sys
from langchain_core.documents import Document

from app.rag.cleaner import DocumentCleaner, document_cleaner

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def test_remove_control_characters():
    dirty = "长沙\u200b工业\ufeff学院\x00\x08测试"
    cleaned = DocumentCleaner.remove_control_characters(dirty)
    assert cleaned == "长沙工业学院测试", f"Control char cleaning failed: {cleaned}"
    print("[PASS] test_remove_control_characters")


def test_remove_page_numbers():
    text = (
        "# 学校介绍\n"
        "长沙工业学院位于湖南省长沙市。\n"
        "第 1 页 共 10 页\n"
        "校园占地面积广阔。\n"
        "- 2 -\n"
        "Page 3 of 10\n"
        "· 4 ·\n"
        "图书馆藏书丰富。\n"
    )
    cleaned = DocumentCleaner.clean_text(text)
    assert "第 1 页" not in cleaned
    assert "- 2 -" not in cleaned
    assert "Page 3" not in cleaned
    assert "· 4 ·" not in cleaned
    assert "长沙工业学院位于湖南省长沙市。" in cleaned
    assert "图书馆藏书丰富。" in cleaned
    print("[PASS] test_remove_page_numbers")


def test_clean_markdown_tables():
    text = (
        "| 专业 | 计划数 | 最低分 |\n"
        "| :--- | :---: | :---: |\n"
        "| 计算机科学与技术 | 100 | 500 |\n"
        "| | | |\n"
        "| - | -- | — |\n"
        "| 软件工程 | 80 | 490 |\n"
    )
    cleaned = DocumentCleaner.clean_markdown_tables(text)
    assert "| 计算机科学与技术 | 100 | 500 |" in cleaned
    assert "| 软件工程 | 80 | 490 |" in cleaned
    assert "| | | |" not in cleaned
    assert "| - | -- | — |" not in cleaned
    print("[PASS] test_clean_markdown_tables")


def test_clean_empty_headings():
    text = (
        "# 正常标题\n"
        "正文内容\n"
        "## \n"
        "### \n"
        "### 另一标题\n"
        "内容2"
    )
    cleaned = DocumentCleaner.clean_empty_headings(text)
    assert "## \n" not in cleaned
    assert "### \n" not in cleaned
    assert "# 正常标题" in cleaned
    assert "### 另一标题" in cleaned
    print("[PASS] test_clean_empty_headings")


def test_fix_chinese_linebreaks():
    text = (
        "长沙工业学院\n"
        "是经教育部批准设立的\n"
        "公办普通本科高校。\n"
        "\n"
        "- 列表项一\n"
        "- 列表项二\n"
        "\n"
        "# 标题一\n"
        "第二段内容。"
    )
    cleaned = DocumentCleaner.fix_chinese_linebreaks(text)
    assert "长沙工业学院是经教育部批准设立的公办普通本科高校。" in cleaned
    assert "- 列表项一\n- 列表项二" in cleaned
    assert "# 标题一\n第二段内容。" in cleaned
    print("[PASS] test_fix_chinese_linebreaks")


def test_normalize_whitespace():
    text = "段落一\n\n\n\n\n段落二\r\n\r\n段落三"
    cleaned = DocumentCleaner.normalize_whitespace(text)
    assert "\n\n\n" not in cleaned
    assert "段落一\n\n段落二\n\n段落三" == cleaned
    print("[PASS] test_normalize_whitespace")


def test_clean_documents():
    docs = [
        Document(
            page_content="欢迎来到\u200b长工大！\n第 1 页\n\n\n环境优美。",
            metadata={"source": "test.pdf"},
        ),
        Document(
            page_content="   \u200b  \n\n第 2 页\n   ",
            metadata={"source": "empty.pdf"},
        ),
    ]
    cleaned = document_cleaner.clean_documents(docs)
    assert len(cleaned) == 1
    assert "欢迎来到长工大！" in cleaned[0].page_content
    assert "第 1 页" not in cleaned[0].page_content
    assert cleaned[0].metadata.get("cleaned") is True
    print("[PASS] test_clean_documents")


def main():
    print("=== 开始运行 DocumentCleaner 单元测试 ===")
    test_remove_control_characters()
    test_remove_page_numbers()
    test_clean_markdown_tables()
    test_clean_empty_headings()
    test_fix_chinese_linebreaks()
    test_normalize_whitespace()
    test_clean_documents()
    print("=== DocumentCleaner 全部 7 项测试 100% 通过！ ===")


if __name__ == "__main__":
    main()
