"""Picks a sensible default dashboard scale from the actual screen size -
see ui/dashboard.py's Dashboard.set_scale(). Built after a real report: the
dashboard was tuned on a 4K/200%-Windows-scaling dev display (which reads
comfortably spaced there) but looked visibly cramped on a 1920x1080/100%
laptop - same logical-pixel dashboard, much less physical screen for it.

Classifies by *logical* pixel width (what Qt layouts actually work with,
already DPI-adjusted by Qt/Windows) rather than raw physical resolution -
a 4K display at 200% Windows scaling has the same ~1920 logical-pixel
budget as a plain 1080p/100% display, and should get the same default.
"""
from __future__ import annotations

# Canonical values - ui/dashboard.py imports these rather than the other
# way around, keeping core/ free of any ui/ dependency.
DASHBOARD_SCALE_SMALL = 0.75
DASHBOARD_SCALE_MEDIUM = 1.0
DASHBOARD_SCALE_LARGE = 1.25

# Thresholds on available logical screen width - a real 1920x1080/100%
# laptop (confirmed cramped-looking by an actual user report) must land in
# the compact bucket, not the middle one; only genuinely spacious
# 2K/4K-class logical widths get the larger default.
_SMALL_WIDTH_MAX = 1920
_LARGE_WIDTH_MIN = 2560


def auto_dashboard_scale(available_width: int) -> float:
    if available_width <= _SMALL_WIDTH_MAX:
        return DASHBOARD_SCALE_SMALL
    if available_width >= _LARGE_WIDTH_MIN:
        return DASHBOARD_SCALE_LARGE
    return DASHBOARD_SCALE_MEDIUM


def detect_available_width(screen) -> int:
    """`screen` is a QScreen (e.g. QApplication.primaryScreen() or
    window.screen()) - kept as a thin, barely-there wrapper so the actual
    decision logic above stays unit-testable without a QApplication."""
    return screen.availableGeometry().width()
