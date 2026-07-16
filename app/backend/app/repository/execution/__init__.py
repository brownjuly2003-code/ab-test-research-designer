"""Execution ingestion and aggregate read models.

Public composition: `_ExecutionMixin`. Domain blocks live in sibling modules so
ingestion and heavy rollups stay readable. Import path
`repository._execution._ExecutionMixin` remains a stable facade.
"""

from .cuped import _CupedRollupMixin
from .ingestion import _IngestionMixin
from .primary import _PrimaryRollupMixin
from .quality import _QualityRollupMixin
from .ratio import _RatioRollupMixin
from .strata import _StrataRollupMixin


class _ExecutionMixin(
    _IngestionMixin,
    _PrimaryRollupMixin,
    _QualityRollupMixin,
    _StrataRollupMixin,
    _CupedRollupMixin,
    _RatioRollupMixin,
):
    """Facade-preserving composition of execution domain mixins."""


__all__ = ["_ExecutionMixin"]
