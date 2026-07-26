from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, cast

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class JobQueue(Protocol):
    async def enqueue(self, function: str, *args: object) -> None: ...


class ArqJobQueue:
    """arq-backed queue; the pool is created in the application lifespan."""

    def __init__(self, pool: object) -> None:
        self._pool = pool

    async def enqueue(self, function: str, *args: object) -> None:
        enqueue_job = getattr(self._pool, "enqueue_job")  # noqa: B009 - arq pool API
        await enqueue_job(function, *args)


def _session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="database is not configured")
    return cast(async_sessionmaker[AsyncSession], factory)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = _session_factory(request)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_queue(request: Request) -> JobQueue:
    queue = getattr(request.app.state, "job_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="job queue is not available")
    return cast(JobQueue, queue)
