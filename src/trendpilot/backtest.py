from __future__ import annotations

from dataclasses import asdict, dataclass
import pandas as pd

from .config import ScannerConfig
from .indicators import normalize_ohlcv
from .scanner import scan_symbol


@dataclass(slots=True)
class BacktestTrade:
    symbol: str
    signal_date: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float
    exit_reason: str


def run_event_backtest(symbol: str, frame: pd.DataFrame, benchmark: pd.DataFrame, cfg: ScannerConfig) -> list[BacktestTrade]:
    data, bench = normalize_ohlcv(frame), normalize_ohlcv(benchmark)
    trades: list[BacktestTrade] = []
    cursor = 221
    while cursor < len(data) - 1:
        stock_slice = data.iloc[: cursor + 1]
        bench_slice = bench.loc[: stock_slice.index[-1]]
        if len(bench_slice) < 64:
            cursor += 1
            continue
        result = scan_symbol(symbol, stock_slice, bench_slice, cfg)
        if result.setup_state.value != "READY" or result.score < cfg.minimum_score:
            cursor += 1
            continue
        trigger = result.pivot + 0.10 * result.atr
        limit_price = trigger + min(0.35 * result.atr, trigger * 0.005)
        stop_loss = min(max(trigger - 2 * result.atr, trigger * 0.92), trigger * 0.98)
        entry_idx = entry_price = None
        for candidate_idx in range(cursor + 1, min(cursor + 4, len(data))):
            bar = data.iloc[candidate_idx]
            if float(bar["High"]) >= trigger and float(bar["Open"]) <= limit_price:
                possible = max(trigger, float(bar["Open"]))
                if possible <= limit_price:
                    entry_idx, entry_price = candidate_idx, possible
                    break
        if entry_idx is None:
            cursor += 1
            continue
        exit_idx = min(entry_idx + cfg.max_holding_days, len(data) - 1)
        exit_price, exit_reason = float(data.iloc[exit_idx]["Close"]), "time"
        for candidate_idx in range(entry_idx, exit_idx + 1):
            if float(data.iloc[candidate_idx]["Low"]) <= stop_loss:
                exit_idx = candidate_idx
                exit_price = min(stop_loss, float(data.iloc[candidate_idx]["Open"]))
                exit_reason = "stop"
                break
        trades.append(BacktestTrade(symbol, str(data.index[cursor]), str(data.index[entry_idx]), str(data.index[exit_idx]), round(entry_price, 4), round(exit_price, 4), round(exit_price / entry_price - 1, 6), exit_reason))
        cursor = exit_idx + 1
    return trades


def summarize(trades: list[BacktestTrade]) -> dict:
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "average_return": 0.0, "total_compounded_return": 0.0}
    returns = [trade.return_pct for trade in trades]
    compounded = 1.0
    for value in returns:
        compounded *= 1 + value
    return {"trades": len(trades), "win_rate": round(sum(x > 0 for x in returns) / len(returns), 4), "average_return": round(sum(returns) / len(returns), 6), "total_compounded_return": round(compounded - 1, 6), "details": [asdict(trade) for trade in trades]}


def run_vectorbt(close: pd.Series, entries: pd.Series, exits: pd.Series):
    try:
        import vectorbt as vbt
    except ImportError as exc:
        raise RuntimeError("Install the research extra: pip install -e '.[research]'") from exc
    return vbt.Portfolio.from_signals(close, entries, exits, fees=0.001, slippage=0.0005, freq="1D")

