from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from jsonschema import ValidationError as JsonSchemaValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jacaranda_api.db.models import PackageVersion, ResearchPackage
from jacaranda_api.pipeline.cli import repository_root
from jacaranda_api.pipeline.validation import (
    SemanticValidationError,
    validate_renderable_package,
)
from jacaranda_api.routers.deps import get_session
from jacaranda_api.routers.schemas import PackageDetailOut, PackageDocumentUpdate, PackageOut

router = APIRouter(tags=["packages"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _digest(document: dict[str, Any]) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


async def _snapshot(session: AsyncSession, package: ResearchPackage) -> None:
    """Immutable version record for every status transition (audit trail)."""
    latest = await session.scalar(
        select(func.max(PackageVersion.version)).where(PackageVersion.package_id == package.id)
    )
    session.add(
        PackageVersion(
            package_id=package.id,
            version=(latest or 0) + 1,
            status=package.status,
            digest=_digest(package.document),
            document=package.document,
        )
    )


async def _get_or_404(session: AsyncSession, package_id: str) -> ResearchPackage:
    package = await session.get(ResearchPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    return package


def _quality_failures(document: dict[str, Any]) -> list[str]:
    quality = document.get("quality")
    if not isinstance(quality, dict):
        return ["quality block missing"]
    checks = quality.get("checks")
    if not isinstance(checks, list):
        return ["quality checks missing"]
    return [
        str(check.get("check_id"))
        for check in checks
        if isinstance(check, dict) and check.get("result") == "fail"
    ]


def _set_status(package: ResearchPackage, status: str) -> None:
    document = dict(package.document)
    document["status"] = status
    package.document = document
    package.status = status


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
    return await _get_or_404(session, package_id)


@router.post("/packages/{package_id}/verify", response_model=PackageOut)
async def verify_package(package_id: str, session: SessionDep) -> ResearchPackage:
    """Human confirmation that the draft holds up: structure re-validated, no
    hard QC failure. Role enforcement (reviewer) arrives with authentication."""
    package = await _get_or_404(session, package_id)
    if package.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail=f"cannot verify a {package.status} package")
    failures = _quality_failures(package.document)
    if failures:
        raise HTTPException(status_code=409, detail=f"quality checks failed: {failures}")
    try:
        validate_renderable_package(repository_root(), dict(package.document))
    except (SemanticValidationError, JsonSchemaValidationError) as error:
        raise HTTPException(status_code=409, detail=str(error)[:500]) from None
    _set_status(package, "verified")
    await _snapshot(session, package)
    await session.flush()
    return package


@router.post("/packages/{package_id}/approve", response_model=PackageOut)
async def approve_package(package_id: str, session: SessionDep) -> ResearchPackage:
    """Only a human can approve, and a mock package can never be approved —
    the platform's hardest invariant."""
    package = await _get_or_404(session, package_id)
    if package.is_mock or bool(package.document.get("company", {}).get("is_mock")):
        raise HTTPException(status_code=403, detail="mock packages can never be approved")
    if package.status != "verified":
        raise HTTPException(status_code=409, detail="only verified packages can be approved")
    _set_status(package, "approved")
    await _snapshot(session, package)
    await session.flush()
    return package


@router.post("/packages/{package_id}/reject", response_model=PackageOut)
async def reject_package(package_id: str, session: SessionDep) -> ResearchPackage:
    package = await _get_or_404(session, package_id)
    if package.status == "approved":
        raise HTTPException(
            status_code=409, detail="approved packages cannot be rejected; edit instead"
        )
    _set_status(package, "rejected")
    await _snapshot(session, package)
    await session.flush()
    return package


@router.patch("/packages/{package_id}/document", response_model=PackageDetailOut)
async def update_document(
    package_id: str, payload: PackageDocumentUpdate, session: SessionDep
) -> ResearchPackage:
    """Replace the research document after human editing. Any edit drops the
    package back to draft — earlier versions stay downloadable via snapshots."""
    package = await _get_or_404(session, package_id)
    document = dict(payload.document)
    document["status"] = "draft"
    try:
        validate_renderable_package(repository_root(), document)
    except (SemanticValidationError, JsonSchemaValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)[:500]) from None
    package.document = document
    package.status = "draft"
    await _snapshot(session, package)
    await session.flush()
    return package


@router.get("/packages/{package_id}/versions")
async def list_versions(package_id: str, session: SessionDep) -> list[dict[str, Any]]:
    await _get_or_404(session, package_id)
    versions = await session.scalars(
        select(PackageVersion)
        .where(PackageVersion.package_id == package_id)
        .order_by(PackageVersion.version)
    )
    return [
        {
            "version": item.version,
            "status": item.status,
            "digest": item.digest,
            "created_at": item.created_at.isoformat(),
        }
        for item in versions
    ]
