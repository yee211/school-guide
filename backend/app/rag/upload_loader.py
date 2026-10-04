from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

from langchain_core.documents import Document
from markitdown import MarkItDown, StreamInfo

SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".csv",
}

_CONVERSION_LOCK = Lock()


@lru_cache(maxsize=1)
def _get_converter() -> MarkItDown:
    return MarkItDown()


def _build_metadata(
    filename: str,
    title: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title or Path(filename).stem,
        "filename": filename,
        "source": filename,
        "file_type": Path(filename).suffix.lower(),
        "parser": "markitdown",
    }


def load_uploaded_documents(
    filename: str,
    content: bytes,
) -> list[Document]:
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的文件格式：{suffix}")

    if not content:
        raise ValueError("文件内容为空")

    text: str = ""
    title: str | None = None

    try:
        with _CONVERSION_LOCK:
            converter = _get_converter()
            result = converter.convert_stream(
                BytesIO(content),
                stream_info=StreamInfo(
                    extension=suffix,
                    filename=filename,
                ),
            )
            if result and result.markdown:
                text = result.markdown.strip()
            title = getattr(result, "title", None)
    except Exception as exc:
        # 针对纯文本和 Markdown 格式提供编码回退机制
        if suffix in {".txt", ".md"}:
            for encoding in ("utf-8", "gb18030", "gbk"):
                try:
                    text = content.decode(encoding).strip()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError(f"文档解析失败：{exc}") from exc
        else:
            raise ValueError(f"文档解析失败：{exc}") from exc

    if not text:
        raise ValueError("文件中没有可索引的有效文本内容")

    metadata = _build_metadata(filename, title=title)

    return [
        Document(
            page_content=text,
            metadata=metadata,
        )
    ]
