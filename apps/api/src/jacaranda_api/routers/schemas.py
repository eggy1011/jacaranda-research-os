from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    market: str
    company_name_zh: str | None
    company_name_en: str | None
    created_at: datetime
    updated_at: datetime


class RunStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    status: str
    detail: dict[str, Any] | None
    updated_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    symbol: str
    status: str
    attempt: int
    error: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class RunDetailOut(RunOut):
    stages: list[RunStageOut]


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    run_id: str | None
    package_uid: str
    status: str
    is_mock: bool
    created_at: datetime
    updated_at: datetime


class PackageDetailOut(PackageOut):
    document: dict[str, Any]


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    kind: str
    edition: str | None
    path: str
    sha256: str | None
