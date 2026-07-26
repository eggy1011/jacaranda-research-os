from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jacaranda_api.db.models import ResearchPackage
from jacaranda_api.routers.deps import get_session
from jacaranda_api.routers.schemas import PackageDetailOut, PackageOut

router = APIRouter(tags=["packages"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/projects/{project_id}/packages", response_model=list[PackageOut])
async def list_packages(project_id: str, session: SessionDep) -> list[ResearchPackage]:
    result = await session.scalars(
        select(ResearchPackage)
        .where(ResearchPackage.project_id == project_id)
        .order_by(ResearchPackage.created_at.desc())
    )
    return list(result)


@router.get("/packages/{package_id}", response_model=PackageDetailOut)
async def get_package(package_id: str, session: SessionDep) -> ResearchPackage:
    package = await session.get(ResearchPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    return package
