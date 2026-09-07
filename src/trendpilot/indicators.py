from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        raise ValueError("Expected single-symbol OHLCV data")
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    return frame.sort_index().loc[:, ["Open", "High", "Low", "Close", "Volume"]].dropna()


def safe_return(series: pd.Series, periods: int) -> float:
    if len(series) <= periods or float(series.iloc[-periods - 1]) == 0:
        return 0.0
    return float(series.iloc[-1] / series.iloc[-periods - 1] - 1)


def atr(frame: pd.DataFrame, window: int = 14) -> float:
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(true_range.rolling(window).mean().iloc[-1])

