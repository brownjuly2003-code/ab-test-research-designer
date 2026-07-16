"""Facade for live experiment statistics (audit F-11).

Stable import path used by routes and tests. Implementation lives in
``app.backend.app.services.live_stats``.
"""

from app.backend.app.services.live_stats import build_live_stats

__all__ = ["build_live_stats"]
