import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.rag.indexer import add_to_index
from app.rag.loader import BACKEND_DIR, RAW_DATA_DIR
from app.rag.splitter import split_documents
from app.rag.upload_loader import (
    SUPPORTED_EXTENSIONS,
    load_uploaded_documents,
)
from app.structured.parsers import parse_all
from app.structured.store import reload as reload_structured_data

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024
UPLOAD_LOCK = asyncio.Lock()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
):
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()

    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空",
        )

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支持的文件格式：{extension}",
        )

    try:
        content = await file.read(MAX_FILE_SIZE + 1)
    finally:
        await file.close()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="上传的文件为空",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="文件不能超过 10 MB",
        )

    try:
        documents = await asyncio.to_thread(
            load_uploaded_documents,
            filename,
            content,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with UPLOAD_LOCK:
        target_path = RAW_DATA_DIR / filename

        if target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="知识库中已经存在同名文件",
            )

        source = target_path.relative_to(BACKEND_DIR).as_posix()
        for document in documents:
            document.metadata["source"] = source

        uploaded_chunks = split_documents(documents)
        if not uploaded_chunks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="文件清洗后没有可索引的有效文本内容",
            )

        target_path.write_bytes(content)

        try:
            indexed_count = await asyncio.to_thread(
                add_to_index,
                uploaded_chunks,
            )

            # 同步更新结构化招生与录取数据表（如有结构化文件）
            try:
                score_rows, plan_rows = await asyncio.to_thread(
                    parse_all,
                    RAW_DATA_DIR,
                )
                if score_rows or plan_rows:
                    await asyncio.to_thread(
                        reload_structured_data,
                        score_rows,
                        plan_rows,
                    )
            except Exception:
                logger.warning(
                    "结构化数据表同步跳过或失败，不影响向量知识库",
                    exc_info=True,
                )
        except Exception as exc:
            # 建库失败，移除刚保存的文件
            target_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="文件解析成功，但知识库更新失败",
            ) from exc

        return {
            "filename": filename,
            "uploaded_document_count": len(documents),
            "uploaded_chunk_count": len(uploaded_chunks),
            "total_indexed_chunk_count": indexed_count,
        }
