"""Turn a jbr experiment output tree into the per-engine files the loader reads.

jbr writes one directory per factor combination, each holding a
`query-results-raw.json`, and the combination index is the only thing tying a
directory back to the configuration that produced it. That mapping lives in the
experiment's combination provider, not in the output, so it has to be supplied
here - and getting it wrong silently mislabels every figure, which is why the
extraction is a separate, inspectable step rather than something the loader
guesses at.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

COMBINATION_DIR = re.compile(r"^combination_(?P<index>\d+)$")
RAW_NAME = "query-results-raw.json"

#: Combination index -> configuration name, in the order the factors are declared.
DEFAULT_CONFIG_NAMES = [
    "adaptive-derived-resources",
    "default",
    "adaptive",
    "adaptive-derived-resources-no-chain",
    "adaptive-derived-resources-pattern-only",
]


def find_combinations(source: Path) -> dict[int, Path]:
    """Map combination index -> its raw results file."""
    found: dict[int, Path] = {}
    for candidate in sorted(source.rglob(RAW_NAME)):
        for part in candidate.parts:
            match = COMBINATION_DIR.match(part)
            if match:
                index = int(match.group("index"))
                if index in found:
                    raise ValueError(
                        f"combination_{index} appears twice: {found[index]} and {candidate}")
                found[index] = candidate
                break
    if not found:
        raise FileNotFoundError(f"no {RAW_NAME} under any combination_* directory in {source}")
    return found


def extract(
    source: Path,
    dest: Path,
    config_names: list[str] | None = None,
) -> dict[str, Path]:
    """Copy each combination's results to `query-results-raw-<config>.json`.

    Every combination found must have a name and every name must be used: a
    mismatch means the mapping no longer matches the experiment, and carrying on
    would label the output with the wrong configurations.
    """
    names = config_names or DEFAULT_CONFIG_NAMES
    combinations = find_combinations(source)

    missing = sorted(set(range(len(names))) - set(combinations))
    extra = sorted(set(combinations) - set(range(len(names))))
    if missing or extra:
        raise ValueError(
            f"{len(names)} configuration names given but combinations are "
            f"{sorted(combinations)}"
            + (f"; no directory for {missing}" if missing else "")
            + (f"; no name for {extra}" if extra else ""))

    dest.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for index, name in enumerate(names):
        source_file = combinations[index]
        # Parsed rather than copied, so a truncated or malformed run fails here
        # instead of halfway through the analysis.
        records = json.loads(source_file.read_text())
        target = dest / f"query-results-raw-{name}.json"
        target.write_text(json.dumps(records))
        written[name] = target
    return written


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="directory holding the combination_* output directories")
    parser.add_argument("--dest", type=Path, required=True,
                        help="directory to write query-results-raw-<config>.json into")
    parser.add_argument("--names", nargs="*", default=None,
                        help="configuration names, in combination index order")
    args = parser.parse_args()

    written = extract(args.source, args.dest, args.names)
    combinations = find_combinations(args.source)
    for index, (name, path) in enumerate(written.items()):
        records = json.loads(path.read_text())
        print(f"  combination_{index} -> {name:<42} {len(records):>5} runs   ({combinations[index]})")
    print(f"\nwrote {len(written)} files to {args.dest}")


if __name__ == "__main__":
    main()
