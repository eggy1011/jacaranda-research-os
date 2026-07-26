from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jacaranda_api.db.models import Project, Run
from jacaranda_api.routers.deps import JobQueue, get_queue, get_session
from jacaranda_api.routers.schemas import RunDetailOut, RunOut

router = APIRouter(tags=["runs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]


@router.post("/projects/{project_id}/runs", response_model=RunOut, status_code=202)
async def create_run(project_id: str, session: SessionDep, queue: QueueDep) -> Run:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    active = await session.scalar(
        select(Run).where(Run.project_id == project_id, Run.status.in_(("queued", "running")))
    )
    if active is not None:
        raise HTTPException(status_code=409, detail=f"run {active.id} is already in progress")
    run = Run(project_id=project_id, symbol=project.symbol, status="queued")
    session.add(run)
    await session.flush()
    await queue.enqueue("execute_run", run.id)
    return run


@router.get("/projects/{project_id}/runs", response_model=list[RunOut])
async def list_runs(project_id: str, session: SessionDep) -> list[Run]:
    result = await session.scalars(
        select(Run).where(Run.project_id == project_id).order_by(Run.created_at.desc())
    )
    return list(result)


@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: str, session: SessionDep) -> Run:
    run = await session.scalar(
        select(Run).where(Run.id == run_id).options(selectinload(Run.stages))
    )
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/runs/{run_id}/retry", response_model=RunOut, status_code=202)
async def retry_run(run_id: str, session: SessionDep, queue: QueueDep) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != "failed":
        raise HTTPException(status_code=409, detail="only failed runs can be retried")
    run.status = "queued"
    run.error = None
    await session.flush()
    await queue.enqueue("execute_run", run.id)
    return run
