from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on Postgres, plain JSON elsewhere (tests run on SQLite).
JsonColumn = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    market: Mapped[str] = mapped_column(String(8), default="CN-A")
    company_name_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=True
    )

    runs: Mapped[list[Run]] = relationship(back_populates="project")
    packages: Mapped[list[ResearchPackage]] = relationship(back_populates="project")


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="runs")
    stages: Mapped[list[RunStage]] = relationship(
        back_populates="run", order_by="RunStage.created_at"
    )
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="run")


class RunStage(TimestampMixin, Base):
    __tablename__ = "run_stages"
    __table_args__ = (UniqueConstraint("run_id", "key", name="uq_run_stage_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running")
    detail: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)

    run: Mapped[Run] = relationship(back_populates="stages")


class Upload(TimestampMixin, Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="stored")
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)


class ResearchPackage(TimestampMixin, Base):
    __tablename__ = "packages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("runs.id"), nullable=True)
    package_uid: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    document: Mapped[dict[str, Any]] = mapped_column(JsonColumn)

    project: Mapped[Project] = relationship(back_populates="packages")
    versions: Mapped[list[PackageVersion]] = relationship(
        back_populates="package", order_by="PackageVersion.version"
    )


class PackageVersion(TimestampMixin, Base):
    __tablename__ = "package_versions"
    __table_args__ = (
        UniqueConstraint("package_id", "version", name="uq_package_version"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    package_id: Mapped[str] = mapped_column(String(32), ForeignKey("packages.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    digest: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JsonColumn)

    package: Mapped[ResearchPackage] = relationship(back_populates="versions")


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    edition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run: Mapped[Run] = relationship(back_populates="artifacts")
