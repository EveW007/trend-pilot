from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def download_daily(symbols: list[str], years: int = 3) -> dict[str, pd.DataFrame]:
    unique = sorted(set(symbols))
    end = datetime.now() + timedelta(days=1)
    start = end - timedelta(days=365 * years + 30)
    raw = yf.download(
        unique,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    result: dict[str, pd.DataFrame] = {}
    if len(unique) == 1:
        result[unique[0]] = raw
        return result
    for symbol in unique:
        if symbol in raw.columns.get_level_values(0):
            frame = raw[symbol].dropna(how="all")
            if not frame.empty:
                result[symbol] = frame
    return result


def download_daily_batched(
    symbols: list[str],
    years: int = 2,
    batch_size: int = 75,
    on_batch=None,
) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    unique = list(dict.fromkeys(symbols))
    for start in range(0, len(unique), batch_size):
        batch = unique[start : start + batch_size]
        try:
            output.update(download_daily(batch, years=years))
        except Exception as exc:
            if on_batch:
                on_batch(start, len(unique), len(output), str(exc))
            continue
        if on_batch:
            on_batch(min(start + len(batch), len(unique)), len(unique), len(output), None)
    return output
