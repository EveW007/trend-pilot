from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def download_daily(symbols: list[str], years: int = 2) -> dict[str, pd.DataFrame]:
    symbols = list(dict.fromkeys(symbols))
    end = datetime.now() + timedelta(days=1)
    start = end - timedelta(days=365 * years + 30)
    raw = yf.download(symbols, start=start, end=end, auto_adjust=True, group_by="ticker", threads=True, progress=False)
    if len(symbols) == 1:
        return {symbols[0]: raw.dropna(how="all")}
    return {symbol: raw[symbol].dropna(how="all") for symbol in symbols if symbol in raw.columns.get_level_values(0)}


def download_daily_batched(symbols: list[str], years: int = 2, batch_size: int = 75, on_batch=None) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    unique = list(dict.fromkeys(symbols))
    for start in range(0, len(unique), batch_size):
        batch = unique[start : start + batch_size]
        error = None
        try:
            output.update(download_daily(batch, years))
        except Exception as exc:
            error = str(exc)
        if on_batch:
            on_batch(min(start + len(batch), len(unique)), len(unique), len(output), error)
    return output
