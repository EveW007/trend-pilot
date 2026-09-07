from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import ScannerConfig
from .indicators import atr, finite, normalize_ohlcv, safe_return
from .models import ScanResult, SetupState


@dataclass(slots=True)
class VCPMetrics:
    box_width_pct: float
    dry_up_ratio: float
    contraction_ratio: float
    pivot: float
    distance_to_pivot_pct: float
    relative_volume: float
    atr_value: float
    contraction_pass: bool


def _stage2(data: pd.DataFrame, benchmark: pd.DataFrame) -> tuple[int, int, bool, float, list[str]]:
    close = data["Close"]
    latest = float(close.iloc[-1])
    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()
    high52 = float(data["High"].tail(252).max())
    low52 = float(data["Low"].tail(252).min())
    rs63 = safe_return(close, 63) - safe_return(benchmark["Close"], 63)
    rules = [
        (latest > float(sma150.iloc[-1]) and latest > float(sma200.iloc[-1]), "价格高于150/200日均线"),
        (float(sma150.iloc[-1]) > float(sma200.iloc[-1]), "150日均线高于200日均线"),
        (float(sma200.iloc[-1]) > float(sma200.iloc[-21]), "200日均线至少连续一个月向上"),
        (float(sma50.iloc[-1]) > float(sma150.iloc[-1]) > float(sma200.iloc[-1]), "50/150/200日均线多头排列"),
        (latest > float(sma50.iloc[-1]), "价格高于50日均线"),
        (latest >= 1.30 * low52, "价格较52周低点至少高30%"),
        (latest >= 0.75 * high52, "价格位于52周高点25%以内"),
        (rs63 > 0, "最近63日跑赢SPY"),
    ]
    passed = sum(bool(rule) for rule, _ in rules)
    reasons = [label for rule, label in rules if rule]
    return passed, len(rules), passed >= 7, rs63, reasons


def _vcp_metrics(data: pd.DataFrame, cfg: ScannerConfig) -> VCPMetrics:
    lookback = cfg.vcp_lookback
    history = data.iloc[-lookback - 1 : -1]
    if len(history) < lookback:
        raise ValueError(f"Need at least {lookback + 1} rows for VCP analysis")
    pivot = float(history["High"].max())
    close = float(data["Close"].iloc[-1])
    box_low = float(history["Low"].min())
    box_width = (pivot - box_low) / max(pivot, 1e-9)

    # NumPy 1.x + pandas 3 can coerce DataFrames to ndarrays in
    # ``array_split``. Split positional indices so column labels survive.
    segments = [history.iloc[indexes] for indexes in np.array_split(np.arange(len(history)), 3)]
    ranges = [
        float((part["High"].max() - part["Low"].min()) / max(part["Close"].mean(), 1e-9))
        for part in segments
    ]
    contraction_ratio = ranges[-1] / max(ranges[0], 1e-9)
    contraction_pass = ranges[0] > ranges[1] > ranges[2] or contraction_ratio <= 0.70

    vol20 = float(data["Volume"].iloc[-21:-1].mean())
    recent_vol5 = float(data["Volume"].iloc[-6:-1].mean())
    dry_up = recent_vol5 / max(vol20, 1.0)
    latest_volume = float(data["Volume"].iloc[-1])
    relative_volume = latest_volume / max(vol20, 1.0)
    atr_value = finite(float(atr(data).iloc[-1]))
    distance = (close - pivot) / max(pivot, 1e-9)
    return VCPMetrics(
        box_width_pct=box_width,
        dry_up_ratio=dry_up,
        contraction_ratio=contraction_ratio,
        pivot=pivot,
        distance_to_pivot_pct=distance,
        relative_volume=relative_volume,
        atr_value=atr_value,
        contraction_pass=contraction_pass,
    )


def scan_symbol(
    symbol: str,
    frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame,
    cfg: ScannerConfig,
) -> ScanResult:
    data = normalize_ohlcv(frame)
    benchmark = normalize_ohlcv(benchmark_frame)
    if len(data) < 221 or len(benchmark) < 64:
        raise ValueError("At least 221 stock rows and 64 benchmark rows are required")
    passed, total, stage2, rs63, reasons = _stage2(data, benchmark)
    metrics = _vcp_metrics(data, cfg)
    close = float(data["Close"].iloc[-1])
    average_dollar_volume = float((data["Close"] * data["Volume"]).tail(20).mean())
    warnings: list[str] = []
    if close < cfg.minimum_price:
        warnings.append("价格低于最低流动性筛选价")
    if average_dollar_volume < cfg.minimum_average_dollar_volume:
        warnings.append("20日平均成交额低于门槛")

    ready = (
        stage2
        and metrics.box_width_pct <= cfg.max_box_width_pct
        and metrics.contraction_pass
        and metrics.dry_up_ratio <= 0.90
        and -cfg.setup_distance_pct <= metrics.distance_to_pivot_pct <= 0
    )
    triggered = (
        stage2
        and metrics.distance_to_pivot_pct > 0
        and metrics.distance_to_pivot_pct <= 0.03
        and metrics.relative_volume >= cfg.breakout_rvol
    )
    if triggered:
        state = SetupState.TRIGGERED
        reasons.extend(["价格已突破箱体枢轴", "突破成交量达到要求"])
    elif ready:
        state = SetupState.READY
        reasons.extend(["VCP波动收缩", "回调阶段成交量萎缩", "价格接近箱体上沿"])
    elif stage2:
        state = SetupState.WATCH
    else:
        state = SetupState.NONE

    trend_score = passed / total * 40.0
    rs_score = float(np.clip((rs63 + 0.10) / 0.30, 0, 1) * 15)
    contraction_score = 15.0 if metrics.contraction_pass else max(0.0, 15 * (1 - metrics.contraction_ratio))
    dry_score = float(np.clip((1.10 - metrics.dry_up_ratio) / 0.50, 0, 1) * 10)
    proximity_score = float(np.clip(1 - abs(metrics.distance_to_pivot_pct) / 0.08, 0, 1) * 10)
    breakout_score = 10.0 if triggered else (5.0 if ready else 0.0)
    penalty = 10.0 * len(warnings)
    score = float(np.clip(trend_score + rs_score + contraction_score + dry_score + proximity_score + breakout_score - penalty, 0, 100))

    return ScanResult(
        symbol=symbol.upper(),
        as_of=str(data.index[-1]),
        close=round(close, 4),
        stage2_passes=passed,
        stage2_total=total,
        stage2=stage2,
        relative_strength_63d=round(rs63, 6),
        box_width_pct=round(metrics.box_width_pct, 6),
        volume_dry_up_ratio=round(metrics.dry_up_ratio, 6),
        range_contraction_ratio=round(metrics.contraction_ratio, 6),
        pivot=round(metrics.pivot, 4),
        distance_to_pivot_pct=round(metrics.distance_to_pivot_pct, 6),
        relative_volume=round(metrics.relative_volume, 4),
        atr=round(metrics.atr_value, 4),
        setup_state=state,
        score=round(score, 2),
        reasons=reasons,
        warnings=warnings,
    )
