from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jacaranda_api.db.models import Project
from jacaranda_api.market_data.errors import SymbolNormalizationError
from jacaranda_api.pipeline.evidence import resolve_a_share_symbol
from jacaranda_api.routers.deps import get_session
from jacaranda_api.routers.schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectCreate, session: SessionDep) -> Project:
    try:
        symbol = resolve_a_share_symbol(payload.symbol)
    except SymbolNormalizationError as error:
        raise HTTPException(status_code=422, detail=error.message) from None
    project = Project(symbol=symbol.canonical, market=symbol.market.value)
    session.add(project)
    await session.flush()
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(session: SessionDep) -> list[Project]:
    result = await session.scalars(select(Project).order_by(Project.created_at.desc()))
    return list(result)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, session: SessionDep) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project
