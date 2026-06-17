"""Frozen clock for the parsing eval suite. TEST-ONLY.

Production code must NEVER import this module. The frozen ``NOW`` makes
relative-day parsing ("today" / "tomorrow" / "day after tomorrow") and the
default-time rule deterministic in tests.

NOW = 2026-06-15 12:00 (Monday), Asia/Jerusalem wall clock.
"""
from __future__ import annotations

from datetime import datetime

# Asia/Jerusalem wall clock, stored naive (the contract uses local ISO strings).
NOW = datetime(2026, 6, 15, 12, 0, 0)
TZ_NAME = "Asia/Jerusalem"
