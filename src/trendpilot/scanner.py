from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ScannerConfig
from .indicators import atr, normalize_ohlcv, safe_return
from .models import ScanResult, SetupState


def _stage2(data: pd.DataFrame, benchmark: pd.DataFrame) -> tuple[int, bool, float]:
    close = data["Close"]
    latest = float(close.iloc[-1])
    sma50, sma150, sma200 = (close.rolling(days).mean() for days in (50, 150, 200))
    high52, low52 = float(data["High"].tail(252).max()), float(data["Low"].tail(252).min())
    rs63 = safe_return(close, 63) - safe_return(benchmark["Close"], 63)
    rules = [
        latest > float(sma150.iloc[-1]) and latest > float(sma200.iloc[-1]),
        float(sma150.iloc[-1]) > float(sma200.iloc[-1]),
        float(sma200.iloc[-1]) > float(sma200.iloc[-21]),
        float(sma50.iloc[-1]) > float(sma150.iloc[-1]) > float(sma200.iloc[-1]),
        latest > float(sma50.iloc[-1]),
        latest >= 1.30 * low52,
        latest >= 0.75 * high52,
        rs63 > 0,
    ]
    passed = sum(rules)
    return passed, passed >= 7, rs63


def scan_symbol(symbol: str, frame: pd.DataFrame, benchmark_frame: pd.DataFrame, cfg: ScannerConfig) -> ScanResult:
    data, benchmark = normalize_ohlcv(frame), normalize_ohlcv(benchmark_frame)
    if len(data) < 221 or len(benchmark) < 64:
        raise ValueError("Need at least 221 stock rows and 64 benchmark rows")

    passed, stage2, rs63 = _stage2(data, benchmark)
    history = data.iloc[-cfg.vcp_lookback - 1 : -1]
    pivot, box_low = float(history["High"].max()), float(history["Low"].min())
    close = float(data["Close"].iloc[-1])
    box_width = (pivot - box_low) / max(pivot, 1e-9)
    segments = [history.iloc[index] for index in np.array_split(np.arange(len(history)), 3)]
    ranges = [(part["High"].max() - part["Low"].min()) / max(part["Close"].mean(), 1e-9) for part in segments]
    contraction = float(ranges[-1] / max(ranges[0], 1e-9))
    contracts = ranges[0] > ranges[1] > ranges[2] or contraction <= 0.70
    vol20 = float(data["Volume"].iloc[-21:-1].mean())
    dry_up = float(data["Volume"].iloc[-6:-1].mean()) / max(vol20, 1)
    relative_volume = float(data["Volume"].iloc[-1]) / max(vol20, 1)
    distance = (close - pivot) / max(pivot, 1e-9)
    average_dollar_volume = float((data["Close"] * data["Volume"]).tail(20).mean())
    warnings = []
    if close < cfg.minimum_price:
        warnings.append("price below minimum")
    if average_dollar_volume < cfg.minimum_average_dollar_volume:
        warnings.append("20-day average dollar volume below minimum")

    ready = stage2 and box_width <= cfg.max_box_width_pct and contracts and dry_up <= 0.90 and -cfg.setup_distance_pct <= distance <= 0
    triggered = stage2 and 0 < distance <= 0.03 and relative_volume >= cfg.breakout_rvol
    state = SetupState.TRIGGERED if triggered else SetupState.READY if ready else SetupState.WATCH if stage2 else SetupState.NONE
    score = passed / 8 * 45
    score += float(np.clip((rs63 + 0.10) / 0.30, 0, 1) * 15)
    score += 15 if contracts else max(0, 15 * (1 - contraction))
    score += float(np.clip((1.10 - dry_up) / 0.50, 0, 1) * 10)
    score += float(np.clip(1 - abs(distance) / 0.08, 0, 1) * 10)
    score += 5 if ready else 10 if triggered else 0
    score -= 10 * len(warnings)

    return ScanResult(
        symbol=symbol.upper(), as_of=str(data.index[-1]), close=round(close, 4),
        stage2_passes=passed, stage2=stage2,
        momentum_5d=round(safe_return(data["Close"], 5), 6),
        momentum_20d=round(safe_return(data["Close"], 20), 6),
        momentum_63d=round(safe_return(data["Close"], 63), 6),
        relative_strength_63d=round(rs63, 6), box_low=round(box_low, 4), pivot=round(pivot, 4),
        box_width_pct=round(box_width, 6), volume_dry_up_ratio=round(dry_up, 6),
        range_contraction_ratio=round(contraction, 6), distance_to_pivot_pct=round(distance, 6),
        relative_volume=round(relative_volume, 4), atr=round(atr(data), 4), setup_state=state,
        score=round(float(np.clip(score, 0, 100)), 2), warnings=warnings,
    )

