from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jacaranda_api.config import get_settings
from jacaranda_api.db.models import Artifact
from jacaranda_api.routers.deps import get_session
from jacaranda_api.routers.schemas import ArtifactOut

router = APIRouter(tags=["artifacts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(run_id: str, session: SessionDep) -> list[Artifact]:
    result = await session.scalars(
        select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at)
    )
    return list(result)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str, session: SessionDep) -> FileResponse:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    data_root = Path(get_settings().data_dir).resolve()
    path = Path(artifact.path).resolve()
    if not path.is_relative_to(data_root):
        raise HTTPException(status_code=403, detail="artifact path is outside the data root")
    if not path.is_file():
        raise HTTPException(status_code=410, detail="artifact file is gone")
    return FileResponse(path, filename=path.name)
