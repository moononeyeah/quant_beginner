from __future__ import annotations

from dataclasses import dataclass

from config import DEFAULT_ROTATION_LOOKBACK_DAYS


@dataclass
class RotationSpec:
    lookback_days: int = DEFAULT_ROTATION_LOOKBACK_DAYS
