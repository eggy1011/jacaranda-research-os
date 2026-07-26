from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jacaranda_api.config import get_settings
from jacaranda_api.db.models import Project, Upload, new_id
from jacaranda_api.documents.parser import ALLOWED_SUFFIXES
from jacaranda_api.routers.deps import JobQueue, get_queue, get_session
from jacaranda_api.routers.schemas import UploadOut

router = APIRouter(tags=["uploads"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_CHUNK = 1024 * 1024


@router.post("/projects/{project_id}/uploads", response_model=UploadOut, status_code=202)
async def create_upload(
    project_id: str, file: UploadFile, session: SessionDep, queue: QueueDep
) -> Upload:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported file type {suffix or '(none)'}; "
            f"allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}",
        )

    upload_id = new_id()
    target_dir = Path(get_settings().data_dir).resolve() / "uploads" / upload_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    size = 0
    with target.open("wb") as handle:
        while chunk := await file.read(_CHUNK):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                handle.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file exceeds the 50 MB limit")
            handle.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="file is empty")

    upload = Upload(
        id=upload_id,
        project_id=project_id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        path=str(target),
        status="stored",
    )
    session.add(upload)
    await session.flush()
    await queue.enqueue("parse_upload", upload.id)
    return upload


@router.get("/projects/{project_id}/uploads", response_model=list[UploadOut])
async def list_uploads(project_id: str, session: SessionDep) -> list[Upload]:
    result = await session.scalars(
        select(Upload).where(Upload.project_id == project_id).order_by(Upload.created_at.desc())
    )
    return list(result)


@router.get("/uploads/{upload_id}", response_model=UploadOut)
async def get_upload(upload_id: str, session: SessionDep) -> Upload:
    upload = await session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload not found")
    return upload
