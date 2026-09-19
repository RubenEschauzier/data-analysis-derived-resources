"""Shared paths, naming and the validated chart palette."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
FIGURE_DIR = OUTPUT_DIR / "figures"
TABLE_DIR = OUTPUT_DIR / "tables"

# Raw benchmark files are named query-results-raw-<engine>.json.
RAW_GLOB = "query-results-raw-*.json"
RAW_PREFIX = "query-results-raw-"

# Runs that hit the harness timeout report a wall time around this value.
TIMEOUT_MS = 300_000
# Observed timeouts overshoot slightly (up to ~303.5s), so match with tolerance.
TIMEOUT_TOLERANCE = 0.99
# A failure this fast never executed the query -- the engine rejected it.
FAST_FAIL_MS = 1_000

# MD5 of the empty string: the hash a run reports when it produced no results.
EMPTY_HASH = "d41d8cd98f00b204e9800998ecf8427e"

# Categorical slots from the data-viz reference palette, in fixed order.
# Validated with scripts/validate_palette.js (adjacent pairlist, light + dark).
# Forms that need all-pairs separation (scatter, small multiples) cap at 3 slots.
SERIES_LIGHT = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]
SERIES_DARK = [
    "#3987e5", "#d95926", "#199e70", "#c98500",
    "#d55181", "#008300", "#9085e9", "#e66767",
]

# Status palette - fixed, never themed, and deliberately distinct from the
# categorical slots. A status colour never carries meaning alone: every use
# below is paired with a visible label.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Run outcomes mapped onto those reserved roles.
OUTCOME_STATUS = {
    "ok": STATUS["good"],
    "timeout": STATUS["warning"],
    "crash": STATUS["critical"],
    "unsupported": STATUS["serious"],
}

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "text_primary": "#0b0b0b",
        "text_secondary": "#52514e",
        "text_muted": "#7a7975",
        "grid": "#e4e3df",
        "series": SERIES_LIGHT,
    },
    "dark": {
        "surface": "#1a1a19",
        "text_primary": "#ffffff",
        "text_secondary": "#c3c2b7",
        "text_muted": "#8f8e86",
        "grid": "#333330",
        "series": SERIES_DARK,
    },
}


def series_color(theme: str, index: int) -> str:
    """Categorical hues are assigned in fixed order and never cycled."""
    slots = THEMES[theme]["series"]
    if index >= len(slots):
        raise ValueError(
            f"{index + 1} series requested but only {len(slots)} categorical slots "
            "exist; fold the extra engines into small multiples instead of cycling hues."
        )
    return slots[index]
