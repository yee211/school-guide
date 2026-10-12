import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Query, status

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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="上传的文件为空",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

        uploaded_chunks = await asyncio.to_thread(split_documents, documents)
        if not uploaded_chunks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="文件清洗后没有可索引的有效文本内容",
            )

        try:
            with target_path.open("xb") as output:
                output.write(content)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="知识库中已经存在同名文件") from exc
        structured_synced = True

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
                structured_synced = False
                logger.error(
                    "结构化数据同步失败：向量已更新，需要重新运行结构化导入",
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
            "structured_synced": structured_synced,
            "warning": None if structured_synced else "结构化数据未同步，请联系管理员重新导入",
            "filename": filename,
            "uploaded_document_count": len(documents),
            "uploaded_chunk_count": len(uploaded_chunks),
            "total_indexed_chunk_count": indexed_count,
        }


@router.get("/source")
async def preview_source(source: str = Query(min_length=1, max_length=500)):
    """Read only source files confined to the raw knowledge directory."""
    normalized = source.replace("\\", "/")
    if normalized.startswith("backend/"):
        normalized = normalized[len("backend/"):]
    if not normalized.startswith("data/raw/") or any(part in ("..", ".", "") for part in normalized.split("/")):
        raise HTTPException(status_code=400, detail="无效的资料路径")
    path = (BACKEND_DIR / normalized).resolve()
    if not path.is_relative_to(RAW_DATA_DIR.resolve()):
        raise HTTPException(status_code=400, detail="无效的资料路径")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="资料不存在或已更新")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="暂不支持预览此格式")
    if path.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="资料较大，暂不支持在线预览")

    def read_content():
        data = path.read_bytes()
        if path.suffix.lower() in {".md", ".txt", ".csv"}:
            for encoding in ("utf-8-sig", "gb18030"):
                try:
                    return data.decode(encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError("资料编码无法识别")
        docs = load_uploaded_documents(path.name, data)
        return "\n\n".join(doc.page_content for doc in docs)

    try:
        content = await asyncio.to_thread(read_content)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="资料暂时无法预览") from exc
    limit = 60000
    return {"title": path.stem, "source": normalized, "content": content[:limit], "truncated": len(content) > limit}
