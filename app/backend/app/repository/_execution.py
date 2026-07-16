"""Facade for execution ingestion/rollups (audit F-11).

Stable import path used by SQLite/Postgres backends. Implementation lives in
`app.backend.app.repository.execution`.
"""

from app.backend.app.repository.execution import _ExecutionMixin

__all__ = ["_ExecutionMixin"]
