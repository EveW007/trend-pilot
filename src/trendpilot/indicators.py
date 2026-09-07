from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        raise ValueError("Expected a single-symbol OHLCV frame")
    missing = REQUIRED_COLUMNS.difference(data.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    data = data.sort_index().loc[:, ["Open", "High", "Low", "Close", "Volume"]]
    return data.dropna(subset=["Open", "High", "Low", "Close"])


def true_range(data: pd.DataFrame) -> pd.Series:
    previous_close = data["Close"].shift(1)
    parts = pd.concat(
        [
            data["High"] - data["Low"],
            (data["High"] - previous_close).abs(),
            (data["Low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return parts.max(axis=1)


def atr(data: pd.DataFrame, window: int = 14) -> pd.Series:
    return true_range(data).rolling(window).mean()


def safe_return(series: pd.Series, periods: int) -> float:
    if len(series) <= periods or float(series.iloc[-periods - 1]) == 0:
        return 0.0
    return float(series.iloc[-1] / series.iloc[-periods - 1] - 1.0)


def finite(value: float, fallback: float = 0.0) -> float:
    return float(value) if np.isfinite(value) else fallback

