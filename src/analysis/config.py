"""Shared paths, naming and the validated chart palette."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def output_dir_for(data_dir: Path) -> Path:
    """Where analysis output belongs for a given data directory.

    A sibling of the data directory, named by swapping a leading `data` for
    `output`: `data/` writes to `output/`, `data-no-delay/` to `output-no-delay/`.
    That keeps each dataset's results beside the data that produced them and stops a
    second dataset from silently overwriting the first's tables and figures, which is
    what a single fixed output directory invites.

    A directory not named after `data` takes an `output-` prefix instead, so an
    extraction directory like `.../extracted` lands next to itself rather than
    colliding with an `output/` that may already hold raw experiment output.
    """
    name = data_dir.name
    if name == "data":
        derived = "output"
    elif name.startswith(("data-", "data_")):
        derived = f"output{name[len('data'):]}"
    else:
        derived = f"output-{name}"
    return data_dir.parent / derived
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

# Dash patterns paired with the categorical slots, in the same fixed order.
#
# The palette clears its gates on the adjacent pairlist, which is the one lines are
# read on, but not on all pairs: with five series on screen a reader may compare any
# two, and `#e87ba4` vs `#eb6834` measures 12.9 normal-vision (below the 15 floor),
# `#d55181` vs `#199e70` 1.6 under deutan on the dark surface. Dash carries the
# identity that hue cannot at that distance, so the series stay separable without
# colour - which also covers print and forced-colours.
SERIES_DASHES = [
    (0, ()),
    (0, (5, 2)),
    (0, (1, 1.6)),
    (0, (7, 2, 1.5, 2)),
    (0, (2.5, 1.6)),
    (0, (5, 2, 1.5, 2, 1.5, 2)),
    (0, (9, 3)),
    (0, (1.5, 1.2, 4, 1.2)),
]


def series_dash(index: int):
    """Dash pattern for a categorical slot, paired one-to-one with `series_color`."""
    if index >= len(SERIES_DASHES):
        raise ValueError(f"no dash pattern for series {index + 1}")
    return SERIES_DASHES[index]


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
