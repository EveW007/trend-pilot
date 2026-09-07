from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


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
class AccountConfig:
    net_liquidation: float = 100_000.0
    risk_per_trade_pct: float = 0.0035
    max_position_pct: float = 0.10
    max_total_open_risk_pct: float = 0.02


@dataclass(slots=True)
class UniverseConfig:
    include_etfs: bool = True
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
class BrokerConfig:
    mode: str = "dry-run"
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 71
    account_id: str = ""
    paper_only: bool = True
    live_trading_enabled: bool = False


@dataclass(slots=True)
class AppConfig:
    database_path: str = "data/trendpilot.sqlite3"
    symbols: list[str] = field(default_factory=lambda: ["META", "MU", "NVDA", "DRAM"])
    benchmark: str = "SPY"
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)


def load_config(path: str | Path) -> AppConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return AppConfig(
        database_path=raw.get("database_path", "data/trendpilot.sqlite3"),
        symbols=[str(symbol).upper() for symbol in raw.get("symbols", [])],
        benchmark=str(raw.get("benchmark", "SPY")).upper(),
        scanner=ScannerConfig(**raw.get("scanner", {})),
        account=AccountConfig(**raw.get("account", {})),
        universe=UniverseConfig(**raw.get("universe", {})),
        broker=BrokerConfig(**raw.get("broker", {})),
    )
