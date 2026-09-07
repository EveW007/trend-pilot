from __future__ import annotations

import numpy as np
import pandas as pd

from trendpilot.config import ScannerConfig
from trendpilot.models import SetupState
from trendpilot.scanner import scan_symbol


def synthetic_frame(rows: int = 300) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=rows)
    base = np.linspace(50, 100, rows)
    close = base.copy()
    # Three progressively tighter ranges immediately before the last bar.
    close[-31:-21] = np.linspace(92, 100, 10) + np.sin(np.arange(10)) * 2.5
    close[-21:-11] = np.linspace(96, 100, 10) + np.sin(np.arange(10)) * 1.2
    close[-11:-1] = np.linspace(98, 100, 10) + np.sin(np.arange(10)) * 0.45
    close[-1] = 100.0
    high = close + 0.35
    low = close - 0.35
    volume = np.full(rows, 2_000_000.0)
    volume[-6:-1] = 1_000_000
    volume[-1] = 2_000_000
    return pd.DataFrame({"Open": close - 0.1, "High": high, "Low": low, "Close": close, "Volume": volume}, index=index)


def test_stage2_vcp_ready_or_watch():
    stock = synthetic_frame()
    benchmark = synthetic_frame()
    benchmark["Close"] = np.linspace(100, 125, len(benchmark))
    benchmark["Open"] = benchmark["Close"] - 0.1
    benchmark["High"] = benchmark["Close"] + 0.2
    benchmark["Low"] = benchmark["Close"] - 0.2
    result = scan_symbol("TEST", stock, benchmark, ScannerConfig(minimum_average_dollar_volume=1_000_000))
    assert result.stage2
    assert result.setup_state in {SetupState.READY, SetupState.WATCH}
    assert 0 <= result.score <= 100

