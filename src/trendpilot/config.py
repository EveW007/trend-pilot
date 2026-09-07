from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AccountConfig:
    net_liquidation: float = 100_000.0
    risk_per_trade_pct: float = 0.0035
    max_position_pct: float = 0.10
    max_total_open_risk_pct: float = 0.02


@dataclass(slots=True)
class ScannerConfig:
    vcp_lookback: int = 30
    max_box_width_pct: float = 0.18
    setup_distance_pct: float = 0.03
    breakout_rvol: float = 1.5
    minimum_price: float = 10.0
    minimum_average_dollar_volume: float = 20_000_000.0
    minimum_score: float = 70.0
    max_holding_days: int = 20


@dataclass(slots=True)
class BrokerConfig:
    mode: str = "dry-run"
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 71
    account_id: str = "DU_PAPER_ACCOUNT"
    paper_only: bool = True
    live_trading_enabled: bool = False


@dataclass(slots=True)
class UniverseConfig:
    source: str = "nasdaq-trader"
    include_etfs: bool = False
    include_adrs: bool = True
    batch_size: int = 75
    recommendation_count: int = 30
    watch_score_floor: float = 60.0
    minimum_market_cap: float = 1_000_000_000.0
    minimum_session_dollar_volume: float = 1_000_000.0
    max_liquid_symbols: int = 1500
    max_recommendations_per_sector: int = 5
    max_recommendations_per_industry: int = 3


@dataclass(slots=True)
class AppConfig:
    database_path: str = "data/trendpilot.sqlite3"
    watchlist: list[str] = field(default_factory=lambda: ["META", "MU", "NVDA"])
    benchmark: str = "SPY"
    account: AccountConfig = field(default_factory=AccountConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)


def _construct(cls: type, raw: dict[str, Any] | None):
    return cls(**(raw or {}))


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return AppConfig(
        database_path=raw.get("database_path", "data/trendpilot.sqlite3"),
        watchlist=[str(x).upper() for x in raw.get("watchlist", ["META", "MU", "NVDA"])],
        benchmark=str(raw.get("benchmark", "SPY")).upper(),
        account=_construct(AccountConfig, raw.get("account")),
        scanner=_construct(ScannerConfig, raw.get("scanner")),
        universe=_construct(UniverseConfig, raw.get("universe")),
        broker=_construct(BrokerConfig, raw.get("broker")),
    )
