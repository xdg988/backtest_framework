"""Strategy 69 alias: stable-dog ETF rotation (reuses strategy 14 logic)."""

from __future__ import annotations

from .s14_etf_safe_dog_rotation import ETFSafeDogRotation


class ETFStableDogRotation(ETFSafeDogRotation):
    """Alias class for strategy 69; behavior matches ETFSafeDogRotation."""
