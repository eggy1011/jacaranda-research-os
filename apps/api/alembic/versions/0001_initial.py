"""Initial schema: users, projects, runs, run_stages, uploads, packages,
package_versions, artifacts.

Revision ID: 0001
Revises:
Create Date: 2026-07-27
"""
from __future__ import annotations

from alembic import op
from jacaranda_api.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# Tables owned by this revision — pinned so later models added to the metadata
# (e.g. auth tables in 0002) are not created here as well.
_TABLES = (
    "users",
    "projects",
    "runs",
    "run_stages",
    "uploads",
    "packages",
    "package_versions",
    "artifacts",
)


def upgrade() -> None:
    # Initial revision only: created from the declarative metadata so the first
    # deploy and the models cannot drift. Later revisions use explicit ops.
    tables = [Base.metadata.tables[name] for name in _TABLES]
    Base.metadata.create_all(op.get_bind(), tables=tables)


def downgrade() -> None:
    tables = [Base.metadata.tables[name] for name in _TABLES]
    Base.metadata.drop_all(op.get_bind(), tables=tables)
