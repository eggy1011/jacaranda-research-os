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


def upgrade() -> None:
    # Initial revision only: created from the declarative metadata so the first
    # deploy and the models cannot drift. Later revisions use explicit ops.
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
