from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jacaranda_api.db.engine import create_engine, create_session_factory
from jacaranda_api.db.models import Base, Project, ResearchPackage
from jacaranda_api.main import create_app
from jacaranda_api.pipeline.export import PdfExportError, convert_pptx_to_pdf, find_soffice

ROOT = Path(__file__).resolve().parents[3]


def _fixture_document(*, is_mock: bool, status: str = "draft") -> dict[str, Any]:
    document = json.loads(
        (ROOT / "packages/presentation/fixtures/mock-package.json").read_text(encoding="utf-8")
    )
    document["status"] = status
    document["company"]["is_mock"] = is_mock
    return document


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
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app("test")
    app.state.session_factory = db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def _seed_package(
    db: async_sessionmaker[AsyncSession], *, is_mock: bool, status: str = "draft"
) -> str:
    async with db() as session:
        project = Project(symbol="600519.SS", market="CN-A")
        session.add(project)
        await session.flush()
        package = ResearchPackage(
            project_id=project.id,
            package_uid="RPK-TEST-2026-001",
            status=status,
            is_mock=is_mock,
            document=_fixture_document(is_mock=is_mock, status=status),
        )
        session.add(package)
        await session.flush()
        package_id = package.id
        await session.commit()
    return package_id


@pytest.mark.anyio
async def test_verify_then_approve_real_package_with_snapshots(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    package_id = await _seed_package(db, is_mock=False)
    verified = await client.post(f"/packages/{package_id}/verify")
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"

    approved = await client.post(f"/packages/{package_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    versions = (await client.get(f"/packages/{package_id}/versions")).json()
    assert [item["version"] for item in versions] == [1, 2]
    assert [item["status"] for item in versions] == ["verified", "approved"]
    assert all(len(item["digest"]) == 64 for item in versions)

    # approved packages cannot be rejected
    assert (await client.post(f"/packages/{package_id}/reject")).status_code == 409


@pytest.mark.anyio
async def test_mock_package_can_verify_but_never_approve(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    package_id = await _seed_package(db, is_mock=True)
    assert (await client.post(f"/packages/{package_id}/verify")).status_code == 200
    denied = await client.post(f"/packages/{package_id}/approve")
    assert denied.status_code == 403
    assert "never be approved" in denied.json()["detail"]


@pytest.mark.anyio
async def test_qc_failure_blocks_verification(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    package_id = await _seed_package(db, is_mock=False)
    async with db() as session:
        package = await session.get(ResearchPackage, package_id)
        assert package is not None
        document = dict(package.document)
        document["quality"] = dict(document["quality"])
        checks = [dict(check) for check in document["quality"]["checks"]]
        checks[0]["result"] = "fail"
        document["quality"]["checks"] = checks
        package.document = document
        await session.commit()
    blocked = await client.post(f"/packages/{package_id}/verify")
    assert blocked.status_code == 409
    assert "QC-01" in blocked.json()["detail"]


@pytest.mark.anyio
async def test_approve_requires_verified_status(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    package_id = await _seed_package(db, is_mock=False)
    assert (await client.post(f"/packages/{package_id}/approve")).status_code == 409


@pytest.mark.anyio
async def test_document_edit_resets_to_draft_and_snapshots(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    package_id = await _seed_package(db, is_mock=False)
    await client.post(f"/packages/{package_id}/verify")

    edited = _fixture_document(is_mock=False)
    edited["disclaimer"] = dict(edited["disclaimer"])
    response = await client.patch(
        f"/packages/{package_id}/document", json={"document": edited}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    versions = (await client.get(f"/packages/{package_id}/versions")).json()
    assert [item["status"] for item in versions] == ["verified", "draft"]

    # a structurally broken edit is refused
    broken = _fixture_document(is_mock=False)
    broken.pop("sections")
    refused = await client.patch(
        f"/packages/{package_id}/document", json={"document": broken}
    )
    assert refused.status_code == 422


class TestPdfExport:
    def test_missing_soffice_is_a_typed_error(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SOFFICE_PATH", raising=False)
        monkeypatch.setattr("jacaranda_api.pipeline.export.shutil.which", lambda _: None)
        monkeypatch.setattr("jacaranda_api.pipeline.export._MACOS_SOFFICE", "/nonexistent")
        assert find_soffice() is None
        with pytest.raises(PdfExportError, match="not installed"):
            convert_pptx_to_pdf(tmp_path / "a.pptx", tmp_path)

    def test_failed_conversion_raises(self, tmp_path: Path) -> None:
        fake = tmp_path / "soffice"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o755)
        with pytest.raises(PdfExportError, match="failed with code 1"):
            convert_pptx_to_pdf(tmp_path / "deck.pptx", tmp_path, soffice=str(fake))

    def test_successful_conversion_returns_pdf_path(self, tmp_path: Path) -> None:
        fake = tmp_path / "soffice"
        # Emulate soffice: create <outdir>/<stem>.pdf (argv: ... --outdir DIR FILE)
        fake.write_text(
            '#!/bin/sh\noutdir="$5"\nsrc="$6"\n'
            'base=$(basename "$src" .pptx)\n'
            'echo pdf > "$outdir/$base.pdf"\n'
        )
        fake.chmod(0o755)
        source = tmp_path / "deck.pptx"
        source.write_bytes(b"pptx")
        produced = convert_pptx_to_pdf(source, tmp_path / "out", soffice=str(fake))
        assert produced.is_file()
        assert produced.name == "deck.pdf"

    @pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
    def test_real_libreoffice_converts_sample_deck(self, tmp_path: Path) -> None:
        sample = ROOT / "packages/presentation/qa/sample-report.zh-CN.pptx"
        produced = convert_pptx_to_pdf(sample, tmp_path)
        assert produced.stat().st_size > 10_000
