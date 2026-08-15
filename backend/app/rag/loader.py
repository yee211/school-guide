from pathlib import Path

from langchain_core.documents import Document

from app.rag.upload_loader import (
    SUPPORTED_EXTENSIONS,
    load_uploaded_documents,
)
from app.core.constants import STRUCTURED_FILENAMES


BACKEND_DIR = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = BACKEND_DIR / "data" / "raw"


def load_knowledge_documents() -> list[Document]:
    documents: list[Document] = []

    file_paths = sorted(
        file_path
        for file_path in RAW_DATA_DIR.rglob("*")
        if (
            file_path.is_file()
            and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
            and file_path.name not in STRUCTURED_FILENAMES
        )
    )

    for file_path in file_paths:
        try:
            file_documents = load_uploaded_documents(
                filename=file_path.name,
                content=file_path.read_bytes(),
            )
        except ValueError as exc:
            raise ValueError(
                f"读取知识库文件失败：{file_path.name}，{exc}"
            ) from exc

        source = file_path.relative_to(BACKEND_DIR).as_posix()

        for document in file_documents:
            document.metadata["source"] = source

        documents.extend(file_documents)

    return documents