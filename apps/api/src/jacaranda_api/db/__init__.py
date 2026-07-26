"""Persistence layer: SQLAlchemy 2 async models, engine factory and Alembic home.

Modelling philosophy (Phase 2): a thin relational spine for identity, status
and timestamps, with the pipeline's existing JSON documents (research package,
checkpoints, attempt records) stored as JSON columns rather than decomposed
into tables that would have to track packages/research-schema forever.
"""
