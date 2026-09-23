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
        )
    )

    for file_path in file_paths:
        # 这些文件的内容已抽进 school_admission_* 结构化表并由精确查询路径
        # 回答；再进向量索引会让同一份数据存在两个来源，检索可能命中与结构
        # 化查询结果冲突的旧文本。
        if file_path.name in STRUCTURED_FILENAMES:
            continue

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