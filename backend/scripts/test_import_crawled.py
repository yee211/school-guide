"""爬取语料导入清洗的轻量回归测试。"""
from scripts.import_crawled import _clean_body


def test_clean_body_keeps_link_labels() -> None:
    body = (
        "正常正文。\n\n"
        "[招生简章](https://example.edu/admission)\n"
        "**附件：**[报名表.docx](< \n"
        "- [专业目录.xlsx](\n"
        "[ ](< \n"
        "* 2026-05-22 校园活动通知 ](</html/news/1.html>) [\n"
        "[[详细]](</news/2.html>)\n"
        "投稿登记表](<\n"
        "附件：[**投稿作品登记表**  \n](<//example.edu/form>)\n\n"
        "发布平台(http://example.edu/news)、有关考核具体安排继续发布。\n"
        "裸链接：https://example.edu/news?id=1，后续正文必须保留。\n"
    )

    cleaned = _clean_body(body)

    assert "正常正文。" in cleaned
    assert "招生简章" in cleaned
    assert "**附件：**报名表.docx" in cleaned
    assert "- 专业目录.xlsx" in cleaned
    assert "校园活动通知" in cleaned
    assert "详细" in cleaned
    assert "投稿登记表" in cleaned
    assert "**投稿作品登记表**" in cleaned
    assert "有关考核具体安排继续发布。" in cleaned
    assert "后续正文必须保留。" in cleaned
    assert "example.edu" not in cleaned
    assert "](" not in cleaned
    assert "</" not in cleaned
    assert "[ ]" not in cleaned


def test_clean_body_removes_images_without_alt_text_leak() -> None:
    cleaned = _clean_body("段落一\n\n![校园图片](https://example.edu/a.png)\n\n段落二")
    assert cleaned == "段落一\n\n段落二"


def main() -> None:
    test_clean_body_keeps_link_labels()
    test_clean_body_removes_images_without_alt_text_leak()
    print("test_import_crawled 全部通过")


if __name__ == "__main__":
    main()
