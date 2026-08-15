import asyncio
from pathlib import Path

from app.rag.indexer import rebuild_index
from app.rag.loader import RAW_DATA_DIR, load_knowledge_documents
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.rag.splitter import split_documents
from app.rag.upload_loader import (
    SUPPORTED_EXTENSIONS,
    load_uploaded_documents,
)


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

    target_path = RAW_DATA_DIR / filename

    if target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库中已经存在同名文件",
        )

    uploaded_chunks = split_documents(documents)

    async with UPLOAD_LOCK:
        target_path = RAW_DATA_DIR / filename

        if target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="知识库中已经存在同名文件",
            )

        target_path.write_bytes(content)

        try:
            all_documents = await asyncio.to_thread(
                load_knowledge_documents,
            )
            all_chunks = split_documents(all_documents)

            indexed_count = await asyncio.to_thread(
                rebuild_index,
                all_chunks,
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
            "total_document_count": len(all_documents),
            "total_indexed_chunk_count": indexed_count,
        }
