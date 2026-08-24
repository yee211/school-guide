"""知识库文档数据清洗与规范化模块。

在文档切分（Chunking）前对原始 Markdown / 文本执行清洗，
剔除 OCR / PDF 解析残留的不可见控制字符、页码、空表格行及断行噪音，
提升切片纯净度与检索精准率。
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# 不可见字符、零宽字符与 ASCII 控制字符（保留 \t \n \r）
_CONTROL_CHAR_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028\u2029\ufeff]"
)

# 常见页码与页眉页脚格式
_PAGE_NUMBER_PATTERNS = (
    # 第 1 页 / 第 1 页 共 10 页 / 第 1/10 页
    re.compile(r"(?m)^\s*第\s*\d+\s*页(?:\s*[/共]\s*\d+\s*页)?\s*$"),
    # - 1 - / -- 1 -- / · 1 ·
    re.compile(r"(?m)^\s*[-—·~～]\s*\d+\s*[-—·~～]\s*$"),
    # Page 1 / Page 1 of 10 / Page 1/10
    re.compile(r"(?m)^\s*Page\s+\d+(?:\s*(?:of|/)\s*\d+)?\s*$", re.IGNORECASE),
    # 纯孤立数字行（多见于 PDF 底部页码）
    re.compile(r"(?m)^\s*\d+\s*$"),
)

# 中文句子结尾正常标点符号集合
_CN_SENTENCE_ENDINGS = set("。！？；：…”.!?;:")

# Markdown 列表前缀或标题特征（不进行中文合并）
_MD_SPECIAL_PREFIXES = (
    "#", "-", "*", "+", ">", "|", "```",
    "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."
)


class DocumentCleaner:
    """文档文本清洗器"""

    @classmethod
    def remove_control_characters(cls, text: str) -> str:
        """清除零宽空格与 ASCII 控制字符"""
        return _CONTROL_CHAR_PATTERN.sub("", text)

    @classmethod
    def remove_page_numbers(cls, text: str) -> str:
        """过滤常见页码与页眉页脚行"""
        cleaned = text
        for pattern in _PAGE_NUMBER_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        return cleaned

    @classmethod
    def clean_markdown_tables(cls, text: str) -> str:
        """移除全空的 Markdown 表格行（如 `| | | |`）"""
        lines = text.splitlines()
        cleaned_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # 检查是否为表格数据行
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [c.strip() for c in stripped[1:-1].split("|")]
                # 若所有单元格均为空字符串或占位破折号，则过滤
                if cells and all(c == "" or c in {"-", "—", "--"} for c in cells):
                    continue
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    @classmethod
    def clean_empty_headings(cls, text: str) -> str:
        """移除只有 # 标记但没有标题文字的空标题行"""
        return re.sub(r"(?m)^\s*#{1,6}\s*$", "", text)

    @classmethod
    def fix_chinese_linebreaks(cls, text: str) -> str:
        """修复 PDF/OCR 导出时在中文句子内部产生的错误换行。

        若上一行以中文字符结尾（且非句末标点），当前行以中文字符开头且非 Markdown 标记，
        则将当前行无缝追加至上一行。
        """
        lines = text.splitlines()
        if len(lines) <= 1:
            return text

        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append(line)
                continue

            if result and result[-1].strip():
                prev_line = result[-1].rstrip()
                last_char = prev_line[-1]
                first_char = stripped[0]

                is_prev_chinese = '\u4e00' <= last_char <= '\u9fff'
                is_next_chinese = '\u4e00' <= first_char <= '\u9fff'
                is_prev_no_punct = last_char not in _CN_SENTENCE_ENDINGS
                is_prev_not_special = not any(
                    prev_line.lstrip().startswith(prefix) for prefix in _MD_SPECIAL_PREFIXES
                )
                is_next_not_special = not any(
                    stripped.startswith(prefix) for prefix in _MD_SPECIAL_PREFIXES
                )

                if (
                    is_prev_chinese
                    and is_next_chinese
                    and is_prev_no_punct
                    and is_prev_not_special
                    and is_next_not_special
                ):
                    result[-1] = prev_line + stripped
                    continue


            result.append(line)

        return "\n".join(result)


    @classmethod
    def normalize_whitespace(cls, text: str) -> str:
        """统一换行符并将多余连续空行压缩为最多两个空行"""
        # 统一换行符
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        # 清除每行末尾的多余空白
        normalized = re.sub(r"[ \t]+(?=\n)", "", normalized)
        # 压缩 3 个以上的连续换行为 2 个换行
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @classmethod
    def clean_text(cls, text: str) -> str:
        """对纯文本执行全流程清洗"""
        if not text:
            return ""

        text = cls.remove_control_characters(text)
        text = cls.remove_page_numbers(text)
        text = cls.clean_markdown_tables(text)
        text = cls.clean_empty_headings(text)
        text = cls.fix_chinese_linebreaks(text)
        text = cls.normalize_whitespace(text)
        return text

    @classmethod
    def clean_document(cls, document: Document) -> Document:
        """清洗单个 Document 对象的 page_content"""
        cleaned_content = cls.clean_text(document.page_content)
        metadata = dict(document.metadata)
        metadata["cleaned"] = True
        return Document(page_content=cleaned_content, metadata=metadata)

    @classmethod
    def clean_documents(
        cls,
        documents: Sequence[Document],
    ) -> list[Document]:
        """批量清洗 Document 列表，并过滤清洗后为空的无效文档"""
        cleaned_docs: list[Document] = []
        for doc in documents:
            cleaned = cls.clean_document(doc)
            if cleaned.page_content:
                cleaned_docs.append(cleaned)
            else:
                logger.debug(
                    "文档清洗后内容为空，已剔除: %s",
                    doc.metadata.get("source", "unknown"),
                )
        return cleaned_docs


# 全局默认单例
document_cleaner = DocumentCleaner()
