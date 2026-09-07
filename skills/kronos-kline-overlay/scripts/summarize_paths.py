#!/usr/bin/env python3
"""Summarize probabilistic OHLC forecast paths without issuing a trade signal."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    current = float(payload["current_close"])
    if current <= 0:
        raise ValueError("current_close must be positive")
    paths = payload.get("paths")
    if not isinstance(paths, list) or not paths:
        raise ValueError("paths must be a non-empty list")

    pivot = payload.get("pivot")
    invalidation = payload.get("invalidation")
    terminal_returns: list[float] = []
    mean_path_returns: list[float] = []
    max_drawdowns: list[float] = []
    cleared_pivot = 0
    touched_invalidation = 0

    for index, path in enumerate(paths):
        closes = [float(value) for value in path.get("close", [])]
        if not closes or any(value <= 0 for value in closes):
            raise ValueError(f"path {index} needs positive close values")
        lows = [float(value) for value in path.get("low", closes)]
        if len(lows) != len(closes):
            raise ValueError(f"path {index} low and close lengths differ")

        terminal_returns.append(closes[-1] / current - 1)
        mean_path_returns.append(statistics.fmean(closes) / current - 1)

        peak = current
        worst = 0.0
        for close in closes:
            peak = max(peak, close)
            worst = min(worst, close / peak - 1)
        max_drawdowns.append(worst)

        if pivot is not None and max(closes) >= float(pivot):
            cleared_pivot += 1
        if invalidation is not None and min(lows) <= float(invalidation):
            touched_invalidation += 1

    count = len(paths)
    result: dict[str, Any] = {
        "symbol": payload.get("symbol"),
        "as_of": payload.get("as_of"),
        "sample_count": count,
        "median_expected_path_return": quantile(mean_path_returns, 0.5),
        "terminal_return_p10": quantile(terminal_returns, 0.10),
        "terminal_return_p50": quantile(terminal_returns, 0.50),
        "terminal_return_p90": quantile(terminal_returns, 0.90),
        "probability_terminal_positive": sum(value > 0 for value in terminal_returns) / count,
        "median_max_drawdown": quantile(max_drawdowns, 0.50),
        "terminal_return_dispersion": statistics.pstdev(terminal_returns),
    }
    if pivot is not None:
        result["probability_clears_pivot"] = cleared_pivot / count
    if invalidation is not None:
        result["probability_touches_invalidation"] = touched_invalidation / count
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON file containing forecast paths")
    parser.add_argument("--output", type=Path, help="Optional output JSON file")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = json.dumps(summarize(payload), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
