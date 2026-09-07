#!/usr/bin/env python3
"""Summarize probabilistic OHLC forecast paths without issuing a trade signal."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def summarize(payload: dict) -> dict:
    current = float(payload["current_close"])
    paths = payload.get("paths")
    if current <= 0 or not isinstance(paths, list) or not paths:
        raise ValueError("positive current_close and non-empty paths are required")
    terminal, mean_returns, drawdowns = [], [], []
    cleared_pivot = touched_invalidation = 0
    for index, path in enumerate(paths):
        closes = [float(value) for value in path.get("close", [])]
        lows = [float(value) for value in path.get("low", closes)]
        if not closes or len(lows) != len(closes) or any(value <= 0 for value in closes):
            raise ValueError(f"invalid path {index}")
        terminal.append(closes[-1] / current - 1)
        mean_returns.append(statistics.fmean(closes) / current - 1)
        peak, worst = current, 0.0
        for close in closes:
            peak, worst = max(peak, close), min(worst, close / max(peak, close) - 1)
        drawdowns.append(worst)
        cleared_pivot += payload.get("pivot") is not None and max(closes) >= float(payload["pivot"])
        touched_invalidation += payload.get("invalidation") is not None and min(lows) <= float(payload["invalidation"])
    count = len(paths)
    result = {
        "sample_count": count,
        "median_expected_path_return": quantile(mean_returns, 0.5),
        "terminal_return_p10": quantile(terminal, 0.10),
        "terminal_return_p50": quantile(terminal, 0.50),
        "terminal_return_p90": quantile(terminal, 0.90),
        "probability_terminal_positive": sum(value > 0 for value in terminal) / count,
        "median_max_drawdown": quantile(drawdowns, 0.50),
        "terminal_return_dispersion": statistics.pstdev(terminal),
    }
    if payload.get("pivot") is not None:
        result["probability_clears_pivot"] = cleared_pivot / count
    if payload.get("invalidation") is not None:
        result["probability_touches_invalidation"] = touched_invalidation / count
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(json.loads(args.input.read_text())), indent=2))


if __name__ == "__main__":
    main()

