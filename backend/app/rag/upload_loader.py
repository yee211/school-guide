from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.object_detection_engine_options import (
    TransformersObjectDetectionEngineOptions,
)
from docling.datamodel.pipeline_options import (
    LayoutObjectDetectionOptions,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.exceptions import ConversionError
from langchain_core.documents import Document

from app.rag.cleaner import document_cleaner



SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
}

_PAGE_METADATA_KEYS = {
    ".pdf": "page",
    ".pptx": "slide",
}
_CONVERSION_LOCK = Lock()


@lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    pdf_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        layout_options=LayoutObjectDetectionOptions(
            engine_options=TransformersObjectDetectionEngineOptions(
                compile_model=False,
            ),
        ),
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pdf_options,
            ),
        },
    )


def _build_metadata(filename: str) -> dict[str, Any]:
    return {
        "title": Path(filename).stem,
        "filename": filename,
        "source": filename,
        "file_type": Path(filename).suffix.lower(),
        "parser": "docling",
    }


def _export_documents(
    filename: str,
    docling_document: Any,
) -> list[Document]:
    suffix = Path(filename).suffix.lower()
    page_metadata_key = _PAGE_METADATA_KEYS.get(suffix)
    pages = getattr(docling_document, "pages", {})

    if page_metadata_key and pages:
        documents: list[Document] = []

        for page_number in sorted(pages):
            text = docling_document.export_to_markdown(
                page_no=page_number,
            ).strip()

            if not text:
                continue

            metadata = _build_metadata(filename)
            metadata[page_metadata_key] = page_number

            documents.append(
                Document(
                    page_content=text,
                    metadata=metadata,
                )
            )

        return documents

    text = docling_document.export_to_markdown().strip()

    if not text:
        return []

    return [
        Document(
            page_content=text,
            metadata=_build_metadata(filename),
        )
    ]


def load_uploaded_documents(
    filename: str,
    content: bytes,
) -> list[Document]:
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的文件格式：{suffix}")

    if not content:
        raise ValueError("文件内容为空")

    source = DocumentStream(
        name=filename,
        stream=BytesIO(content),
    )

    try:
        # Docling 会缓存并复用解析模型；串行转换可避免共享模型被并发调用。
        with _CONVERSION_LOCK:
            result = _get_converter().convert(source)
    except ConversionError as exc:
        raise ValueError(f"无法解析文件：{exc}") from exc
    except Exception as exc:
        raise ValueError(f"文档解析失败：{exc}") from exc

    raw_documents = _export_documents(filename, result.document)
    documents = document_cleaner.clean_documents(raw_documents)

    if not documents:
        raise ValueError("文件中没有可索引的有效文本内容")

    return documents

