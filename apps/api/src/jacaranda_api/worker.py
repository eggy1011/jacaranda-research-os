from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jacaranda_api.config import Settings, get_settings
from jacaranda_api.db.engine import create_engine, create_session_factory
from jacaranda_api.db.models import Artifact, ResearchPackage, Run, RunStage, utc_now
from jacaranda_api.llm.errors import LLMProviderError
from jacaranda_api.market_data.errors import ProviderError
from jacaranda_api.pipeline.cli import repository_root
from jacaranda_api.pipeline.models import PipelineArtifacts
from jacaranda_api.pipeline.real_orchestrator import RealResearchOrchestrator

MAX_TRIES = 3


def _build_orchestrator(
    settings: Settings, root: Path, listener: Any
) -> RealResearchOrchestrator:
    import httpx

    from jacaranda_api.llm.catalog import PromptCatalog
    from jacaranda_api.llm.factory import build_llm_provider
    from jacaranda_api.llm.http_client import HttpxOpenRouterHTTPClient
    from jacaranda_api.market_data.clients.akshare_live import AkshareLiveClient

    http_client = HttpxOpenRouterHTTPClient(
        httpx.AsyncClient(timeout=httpx.Timeout(180.0)),
        base_url=settings.openrouter_base_url,
    )
    llm = build_llm_provider(settings, PromptCatalog(root), http_client)
    return RealResearchOrchestrator(
        root,
        llm=llm,
        akshare_client=AkshareLiveClient(),
        stage_listener=listener,
    )


def _retryable(error: Exception) -> bool:
    if isinstance(error, LLMProviderError | ProviderError):
        return error.retryable
    return False


def _error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, LLMProviderError | ProviderError):
        return error.as_dict()
    return {"code": type(error).__name__, "retryable": False, "message": str(error)[:500]}


async def _upsert_stage(
    session: AsyncSession,
    run_id: str,
    key: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    stage = await session.scalar(
        select(RunStage).where(RunStage.run_id == run_id, RunStage.key == key)
    )
    if stage is None:
        session.add(RunStage(run_id=run_id, key=key, status=status, detail=detail))
    else:
        stage.status = status
        if detail is not None:
            stage.detail = detail
        stage.updated_at = utc_now()


def _llm_usage(document: dict[str, Any]) -> dict[str, Any] | None:
    """Aggregate the pipeline's recorded llm_calls into a per-run usage summary
    (D-008 cost visibility: which model served, how many tokens it spent)."""
    calls = document.get("generation_metadata", {}).get("llm_calls")
    if not isinstance(calls, list) or not calls:
        return None
    models: dict[str, int] = {}
    input_tokens = 0
    output_tokens = 0
    for call in calls:
        if not isinstance(call, dict):
            continue
        model = str(call.get("returned_model", "unknown"))
        models[model] = models.get(model, 0) + 1
        input_tokens += int(call.get("input_tokens") or 0)
        output_tokens += int(call.get("output_tokens") or 0)
    return {
        "calls": len(calls),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "models": models,
    }


async def _record_success(
    session: AsyncSession, run: Run, artifacts: PipelineArtifacts
) -> None:
    document = cast(
        dict[str, Any], json.loads(artifacts.research_package.read_text(encoding="utf-8"))
    )
    existing = await session.scalar(
        select(ResearchPackage).where(ResearchPackage.run_id == run.id)
    )
    if existing is None:
        session.add(
            ResearchPackage(
                project_id=run.project_id,
                run_id=run.id,
                package_uid=str(document["package_id"]),
                status=str(document["status"]),
                is_mock=bool(document["company"]["is_mock"]),
                document=document,
            )
        )
    manifest = cast(
        dict[str, Any], json.loads(artifacts.manifest.read_text(encoding="utf-8"))
    )
    existing_paths = {
        artifact.path
        for artifact in await session.scalars(
            select(Artifact).where(Artifact.run_id == run.id)
        )
    }
    root = artifacts.root
    kinds = {
        "research-package.json": "package",
        "manifest.json": "manifest",
    }
    for item in manifest["artifacts"]:
        raw_path = str(item["path"])
        full = str((root / raw_path).resolve())
        if full in existing_paths:
            continue
        name = Path(raw_path).name
        if name in kinds:
            kind = kinds[name]
        elif name.endswith(".pptx"):
            kind = "pptx"
        elif name.startswith("slide-deck."):
            kind = "deck-json"
        elif name.startswith("overflow-"):
            kind = "overflow-report"
        else:
            kind = "audit"
        edition = None
        for candidate in ("zh-CN", "en-AU"):
            if candidate in name:
                edition = candidate
        session.add(
            Artifact(
                run_id=run.id,
                kind=kind,
                edition=edition,
                path=full,
                sha256=item.get("sha256"),
            )
        )


async def parse_upload(ctx: dict[str, Any], upload_id: str) -> str:
    """arq task: parse a stored upload into locator-addressed blocks."""
    from jacaranda_api.db.models import Upload
    from jacaranda_api.documents.parser import (
        DocumentParseError,
        UnsupportedDocumentError,
        parse_document,
    )

    session_factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    async with session_factory() as session:
        upload = await session.get(Upload, upload_id)
        if upload is None:
            return "missing"
        upload.status = "parsing"
        path = Path(upload.path)
        await session.commit()

    try:
        parsed = parse_document(path)
    except (UnsupportedDocumentError, DocumentParseError, OSError) as error:
        async with session_factory() as session:
            upload = await session.get(Upload, upload_id)
            if upload is not None:
                upload.status = "failed"
                upload.error = {"code": type(error).__name__, "message": str(error)[:500]}
                await session.commit()
        return "failed"

    async with session_factory() as session:
        upload = await session.get(Upload, upload_id)
        if upload is not None:
            upload.status = "parsed"
            upload.parsed = parsed.as_dict()
            upload.error = None
            await session.commit()
    return "parsed"


async def _parsed_uploads(session: AsyncSession, project_id: str) -> list[dict[str, Any]]:
    from jacaranda_api.db.models import Upload

    uploads = await session.scalars(
        select(Upload)
        .where(Upload.project_id == project_id, Upload.status == "parsed")
        .order_by(Upload.created_at)
    )
    payloads: list[dict[str, Any]] = []
    for upload in uploads:
        parsed = upload.parsed or {}
        payloads.append(
            {
                "upload_id": upload.id,
                "filename": upload.filename,
                "created_at": upload.created_at.isoformat(),
                "blocks": parsed.get("blocks", []),
            }
        )
    return payloads


async def execute_run(ctx: dict[str, Any], run_id: str) -> str:
    """arq task: run the real pipeline for a queued run, resuming from disk
    checkpoints on every attempt so retries never re-spend completed stages."""
    session_factory = cast(
        async_sessionmaker[AsyncSession], ctx["session_factory"]
    )
    settings = cast(Settings, ctx["settings"])
    root = cast(Path, ctx["repository_root"])

    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return "missing"
        if run.status == "succeeded":
            return "already-succeeded"
        run.status = "running"
        run.attempt += 1
        run.started_at = run.started_at or utc_now()
        output_dir = str(Path(settings.data_dir).resolve() / "artifacts" / run.id)
        run.output_dir = output_dir
        symbol = run.symbol
        attempt = run.attempt
        uploads = await _parsed_uploads(session, run.project_id)
        await session.commit()

    async def listener(key: str, status: str) -> None:
        async with session_factory() as stage_session:
            await _upsert_stage(stage_session, run_id, key, status)
            await stage_session.commit()

    orchestrator = _build_orchestrator(settings, root, listener)
    try:
        artifacts = await orchestrator.run(
            symbol, Path(output_dir), resume=True, uploads=uploads
        )
    except Exception as error:
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is not None:
                retry = _retryable(error) and attempt < MAX_TRIES
                run.status = "queued" if retry else "failed"
                run.error = _error_payload(error)
                if not retry:
                    run.finished_at = utc_now()
                await session.commit()
        if _retryable(error) and attempt < MAX_TRIES:
            from arq import Retry

            raise Retry(defer=30 * attempt) from error
        raise

    pdf_paths, pdf_failure = _export_pdfs(artifacts)
    await listener("08-pdf-export", "failed" if pdf_failure else "completed")

    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is not None:
            await _record_success(session, run, artifacts)
            document = cast(
                dict[str, Any],
                json.loads(artifacts.research_package.read_text(encoding="utf-8")),
            )
            usage = _llm_usage(document)
            if usage is not None:
                await _upsert_stage(
                    session, run.id, "09-llm-usage", "completed", detail=usage
                )
            for edition, pdf_path in pdf_paths.items():
                existing_pdf = await session.scalar(
                    select(Artifact).where(
                        Artifact.run_id == run.id, Artifact.path == str(pdf_path)
                    )
                )
                if existing_pdf is None:
                    session.add(
                        Artifact(
                            run_id=run.id,
                            kind="pdf",
                            edition=edition,
                            path=str(pdf_path),
                        )
                    )
            run.status = "succeeded"
            # A missing PDF never fails the run: the draft package and PPTX are
            # already useful, and the export can be retried after fixing soffice.
            run.error = {"code": "pdf_export_failed", "message": pdf_failure} if (
                pdf_failure
            ) else None
            run.finished_at = utc_now()
            await session.commit()
    return "succeeded"


def _export_pdfs(artifacts: PipelineArtifacts) -> tuple[dict[str, Path], str | None]:
    from jacaranda_api.pipeline.export import PdfExportError, convert_pptx_to_pdf

    produced: dict[str, Path] = {}
    failure: str | None = None
    for edition, pptx_path in artifacts.pptx.items():
        try:
            produced[edition] = convert_pptx_to_pdf(pptx_path, artifacts.root)
        except (PdfExportError, subprocess.TimeoutExpired) as error:
            failure = str(error)[:300]
    return produced, failure


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)
    ctx["settings"] = settings
    ctx["repository_root"] = repository_root()


async def on_shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    functions = [execute_run, parse_upload]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_tries = MAX_TRIES
    job_timeout = 3600
    # Evaluated at import from the raw env var so importing this module never
    # requires the full validated Settings (tests import execute_run directly).
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379"))
