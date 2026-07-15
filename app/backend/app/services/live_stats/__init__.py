"""Live experiment statistics over ingested exposures/conversions.

Public entry point: ``build_live_stats``. Domain blocks live in sibling modules
(primary, cuped, strata, guardrails, quality) so orchestration stays readable.
The import path ``services.live_stats_service`` remains a stable facade.
"""

from .builder import build_live_stats

__all__ = ["build_live_stats"]
