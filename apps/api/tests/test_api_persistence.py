from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from auth_helpers import sign_in
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import jacaranda_api.worker as worker_module
from jacaranda_api.config import get_settings
from jacaranda_api.db.engine import create_engine, create_session_factory
from jacaranda_api.db.models import Artifact, Base, Project, ResearchPackage, Run, RunStage
from jacaranda_api.llm.errors import LLMRateLimitError
from jacaranda_api.main import create_app
from jacaranda_api.pipeline.models import PipelineArtifacts
from jacaranda_api.worker import execute_run


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...]]] = []

    async def enqueue(self, function: str, *args: object) -> None:
        self.jobs.append((function, args))


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def client(
    db: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[httpx.AsyncClient, FakeQueue]]:
    app = create_app("test")
    queue = FakeQueue()
    app.state.session_factory = db
    app.state.job_queue = queue
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        await sign_in(http, db)
        yield http, queue


@pytest.mark.anyio
async def test_project_crud_and_symbol_normalisation(
    client: tuple[httpx.AsyncClient, FakeQueue],
) -> None:
    http, _ = client
    created = await http.post("/projects", json={"symbol": "600519"})
    assert created.status_code == 201
    body = created.json()
    assert body["symbol"] == "600519.SS"
    assert body["market"] == "CN-A"

    listed = await http.get("/projects")
    assert [item["id"] for item in listed.json()] == [body["id"]]

    fetched = await http.get(f"/projects/{body['id']}")
    assert fetched.status_code == 200
    assert (await http.get("/projects/nope")).status_code == 404


@pytest.mark.anyio
async def test_invalid_symbol_is_rejected(
    client: tuple[httpx.AsyncClient, FakeQueue],
) -> None:
    http, _ = client
    response = await http.post("/projects", json={"symbol": "AAPL"})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_run_lifecycle_enqueues_and_guards_duplicates(
    client: tuple[httpx.AsyncClient, FakeQueue],
    db: async_sessionmaker[AsyncSession],
) -> None:
    http, queue = client
    project_id = (await http.post("/projects", json={"symbol": "600519"})).json()["id"]

    run_response = await http.post(f"/projects/{project_id}/runs")
    assert run_response.status_code == 202
    run_id = run_response.json()["id"]
    assert queue.jobs == [("execute_run", (run_id,))]

    # a queued run blocks a second submission
    assert (await http.post(f"/projects/{project_id}/runs")).status_code == 409

    detail = await http.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "queued"
    assert detail.json()["stages"] == []

    # retry only applies to failed runs
    assert (await http.post(f"/runs/{run_id}/retry")).status_code == 409
    async with db() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        run.status = "failed"
        await session.commit()
    retried = await http.post(f"/runs/{run_id}/retry")
    assert retried.status_code == 202
    assert len(queue.jobs) == 2

    missing = await http.post("/projects/nope/runs")
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_queue_unavailable_returns_503(
    db: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app("test")
    app.state.session_factory = db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        await sign_in(http, db, email="queueless@example.com")
        project_id = (await http.post("/projects", json={"symbol": "600519"})).json()["id"]
        assert (await http.post(f"/projects/{project_id}/runs")).status_code == 503


@pytest.mark.anyio
async def test_package_and_artifact_endpoints(
    client: tuple[httpx.AsyncClient, FakeQueue],
    db: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    http, _ = client
    project_id = (await http.post("/projects", json={"symbol": "600519"})).json()["id"]
    async with db() as session:
        package = ResearchPackage(
            project_id=project_id,
            package_uid="RPK-600519-2026-001",
            status="draft",
            is_mock=False,
            document={"package_id": "RPK-600519-2026-001"},
        )
        session.add(package)
        await session.flush()
        package_id = package.id
        run = Run(project_id=project_id, symbol="600519.SS", status="succeeded")
        session.add(run)
        await session.flush()
        run_id = run.id
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        good = data_dir / "report.zh-CN.pptx"
        good.write_bytes(b"pptx")
        session.add(Artifact(run_id=run_id, kind="pptx", edition="zh-CN", path=str(good)))
        escape_path = str(tmp_path / "escape.json")
        session.add(Artifact(run_id=run_id, kind="package", edition=None, path=escape_path))
        await session.commit()

    packages = (await http.get(f"/projects/{project_id}/packages")).json()
    assert [item["package_uid"] for item in packages] == ["RPK-600519-2026-001"]
    detail = await http.get(f"/packages/{package_id}")
    assert detail.json()["document"]["package_id"] == "RPK-600519-2026-001"
    assert (await http.get("/packages/nope")).status_code == 404

    monkeypatch.setenv("DATABASE_URL", "sqlite:///ignored.db")
    monkeypatch.setenv("REDIS_URL", "redis://ignored")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    try:
        artifacts = (await http.get(f"/runs/{run_id}/artifacts")).json()
        assert len(artifacts) == 2
        by_kind = {item["kind"]: item for item in artifacts}
        ok = await http.get(f"/artifacts/{by_kind['pptx']['id']}/download")
        assert ok.status_code == 200
        assert ok.content == b"pptx"
        outside = await http.get(f"/artifacts/{by_kind['package']['id']}/download")
        assert outside.status_code == 403
    finally:
        get_settings.cache_clear()


class StubOrchestrator:
    """Stands in for RealResearchOrchestrator inside the worker task."""

    def __init__(
        self,
        listener: Any,
        *,
        error: Exception | None = None,
    ) -> None:
        self._listener = listener
        self._error = error

    async def run(
        self,
        symbol: str,
        output_dir: Path,
        *,
        resume: bool = False,
        uploads: list[dict[str, Any]] | None = None,
    ) -> PipelineArtifacts:
        assert resume is True
        await self._listener("01-extraction", "started")
        if self._error is not None:
            await self._listener("01-extraction", "failed")
            raise self._error
        await self._listener("01-extraction", "completed")
        output_dir.mkdir(parents=True, exist_ok=True)
        package_path = output_dir / "research-package.json"
        package_path.write_text(
            json.dumps(
                {
                    "package_id": "RPK-600519-2026-001",
                    "status": "draft",
                    "company": {"is_mock": False},
                }
            ),
            encoding="utf-8",
        )
        pptx = output_dir / "report.zh-CN.pptx"
        pptx.write_bytes(b"pptx")
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "artifacts": [
                        {"path": "research-package.json", "sha256": "abc"},
                        {"path": "manifest.json", "sha256": "def"},
                        {"path": "report.zh-CN.pptx", "kind": "editable-pptx"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return PipelineArtifacts(
            root=output_dir,
            research_package=package_path,
            deck_json={},
            pptx={"zh-CN": pptx},
            overflow_reports={},
            manifest=manifest_path,
            checkpoints=manifest_path,
        )


def _worker_ctx(
    db: async_sessionmaker[AsyncSession], tmp_path: Path, monkeypatch: MonkeyPatch
) -> dict[str, Any]:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///ignored.db")
    monkeypatch.setenv("REDIS_URL", "redis://ignored")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    return {
        "session_factory": db,
        "settings": get_settings(),
        "repository_root": Path(__file__).resolve().parents[3],
    }


async def _make_run(db: async_sessionmaker[AsyncSession]) -> str:
    async with db() as session:
        project = Project(symbol="600519.SS", market="CN-A")
        session.add(project)
        await session.flush()
        run = Run(project_id=project.id, symbol="600519.SS", status="queued")
        session.add(run)
        await session.flush()
        run_id = run.id
        await session.commit()
    return run_id


@pytest.mark.anyio
async def test_worker_success_records_package_stages_artifacts(
    db: async_sessionmaker[AsyncSession], tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    run_id = await _make_run(db)
    ctx = _worker_ctx(db, tmp_path, monkeypatch)
    monkeypatch.setattr(
        worker_module,
        "_build_orchestrator",
        lambda settings, root, listener: StubOrchestrator(listener),
    )
    exported = tmp_path / "report.zh-CN.pdf"
    exported.write_bytes(b"pdf")
    monkeypatch.setattr(
        worker_module, "_export_pdfs", lambda artifacts: ({"zh-CN": exported}, None)
    )
    try:
        outcome = await execute_run(ctx, run_id)
    finally:
        get_settings.cache_clear()
    assert outcome == "succeeded"
    async with db() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        assert run.status == "succeeded"
        assert run.finished_at is not None
        stages = {
            stage.key: stage.status
            for stage in await session.scalars(
                select(RunStage).where(RunStage.run_id == run_id)
            )
        }
        assert stages == {"01-extraction": "completed", "08-pdf-export": "completed"}
        package = await session.scalar(
            select(ResearchPackage).where(ResearchPackage.run_id == run_id)
        )
        assert package is not None
        assert package.status == "draft"
        assert package.is_mock is False
        artifacts = list(
            await session.scalars(select(Artifact).where(Artifact.run_id == run_id))
        )
        kinds = sorted(artifact.kind for artifact in artifacts)
        assert kinds == ["manifest", "package", "pdf", "pptx"]

    # a second invocation is a no-op
    ctx = _worker_ctx(db, tmp_path, monkeypatch)
    try:
        assert await execute_run(ctx, run_id) == "already-succeeded"
    finally:
        get_settings.cache_clear()


@pytest.mark.anyio
async def test_worker_retryable_failure_requeues(
    db: async_sessionmaker[AsyncSession], tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from arq import Retry

    run_id = await _make_run(db)
    ctx = _worker_ctx(db, tmp_path, monkeypatch)
    monkeypatch.setattr(
        worker_module,
        "_build_orchestrator",
        lambda settings, root, listener: StubOrchestrator(
            listener, error=LLMRateLimitError(1)
        ),
    )
    try:
        with pytest.raises(Retry):
            await execute_run(ctx, run_id)
    finally:
        get_settings.cache_clear()
    async with db() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        assert run.status == "queued"
        assert run.error is not None
        assert run.error["code"] == "llm_rate_limited"


@pytest.mark.anyio
async def test_worker_non_retryable_failure_marks_failed(
    db: async_sessionmaker[AsyncSession], tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    run_id = await _make_run(db)
    ctx = _worker_ctx(db, tmp_path, monkeypatch)
    monkeypatch.setattr(
        worker_module,
        "_build_orchestrator",
        lambda settings, root, listener: StubOrchestrator(
            listener, error=RuntimeError("assembly bug")
        ),
    )
    try:
        with pytest.raises(RuntimeError):
            await execute_run(ctx, run_id)
    finally:
        get_settings.cache_clear()
    async with db() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.finished_at is not None
        stages = list(
            await session.scalars(select(RunStage).where(RunStage.run_id == run_id))
        )
        assert [stage.status for stage in stages] == ["failed"]
