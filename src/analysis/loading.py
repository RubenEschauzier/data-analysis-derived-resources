"""Load the raw benchmark JSON into one tidy frame."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .config import (DATA_DIR, EMPTY_HASH, FAST_FAIL_MS, RAW_GLOB, RAW_PREFIX,
                     TIMEOUT_MS, TIMEOUT_TOLERANCE)

_TEMPLATE_RE = re.compile(r"^(?P<prefix>.*?)-(?P<family>[a-z]+)-(?P<index>\d+)$")


def discover_datasets(data_dir: Path = DATA_DIR) -> dict[str, Path]:
    """Map engine name -> raw file, one entry per query-results-raw-*.json."""
    paths = sorted(data_dir.glob(RAW_GLOB))
    if not paths:
        raise FileNotFoundError(f"no files matching {RAW_GLOB} under {data_dir}")
    return {p.stem[len(RAW_PREFIX):]: p for p in paths}


def _failure_kind(failed: bool, timed_out: bool, time_ms: float) -> str:
    """Why a run stopped. Failures are not interchangeable.

    `unsupported` fails in milliseconds having never run; `timeout` ran the full
    budget and was cut off, so its partial output is real progress; `crash`
    stopped part-way for some other reason.
    """
    if not failed:
        return "ok"
    if timed_out:
        return "timeout"
    if time_ms < FAST_FAIL_MS:
        return "unsupported"
    return "crash"


def _template_parts(name: str) -> tuple[str, int]:
    m = _TEMPLATE_RE.match(name)
    if not m:
        return name, 0
    return m.group("family"), int(m.group("index"))


def load_runs(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """One row per individual query execution across every engine.

    Replication index is inferred from the order records appear in the file: the
    harness writes the full template x instance sweep once per replication.
    """
    frames = []
    for engine, path in discover_datasets(data_dir).items():
        records = json.loads(path.read_text())
        frame = pd.DataFrame.from_records(records)
        frame["engine"] = engine
        frame["replication"] = frame.groupby(["name", "id"]).cumcount()
        frames.append(frame)

    df = pd.concat(frames, ignore_index=True)

    df = df.rename(columns={"name": "template", "id": "instance"})
    df["error"] = df.get("error", pd.Series([None] * len(df))).astype("object")
    df["failed"] = df["error"].notna()
    df["timed_out"] = df["time"] >= TIMEOUT_MS * TIMEOUT_TOLERANCE
    df["failure_kind"] = [_failure_kind(f, t, ms)
                          for f, t, ms in zip(df["failed"], df["timed_out"], df["time"])]
    df["empty_result"] = df["hash"].eq(EMPTY_HASH)
    df["n_timestamps"] = df["timestamps"].apply(len)
    df["first_result_ms"] = df["timestamps"].apply(lambda ts: ts[0] if ts else pd.NA)
    df["last_result_ms"] = df["timestamps"].apply(lambda ts: max(ts) if ts else pd.NA)

    # `results` counts what the run actually delivered, errored or not: the
    # timestamp list is the same length on every run in this dataset, so a
    # timed-out run's partial output is a real measurement, not a gap.
    df["delivered"] = df["results"]
    df["throughput_per_s"] = df["delivered"] / (df["time"] / 1000)

    parts = df["template"].map(_template_parts)
    df["family"] = [p[0] for p in parts]
    df["template_index"] = [p[1] for p in parts]

    df = df.drop(columns=["adaptiveStats"], errors="ignore")
    df = df.rename(columns={"httpRequests": "http_requests", "time": "time_ms"})

    order = ["engine", "template", "family", "template_index", "instance",
             "replication", "results", "delivered", "hash", "time_ms",
             "throughput_per_s", "http_requests", "n_timestamps",
             "first_result_ms", "last_result_ms", "failed", "failure_kind",
             "timed_out", "empty_result", "error", "timestamps"]
    return df[[c for c in order if c in df.columns]]


def template_order(df: pd.DataFrame) -> list[str]:
    """Templates sorted by family then numeric index, not lexically."""
    key = df[["template", "family", "template_index"]].drop_duplicates()
    key = key.sort_values(["family", "template_index"])
    return key["template"].tolist()


def engine_order(df: pd.DataFrame) -> list[str]:
    """`default` first when present so it reads as the baseline series."""
    engines = sorted(df["engine"].unique())
    if "default" in engines:
        engines.remove("default")
        engines.insert(0, "default")
    return engines
