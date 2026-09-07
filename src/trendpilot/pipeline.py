from __future__ import annotations

from datetime import UTC, datetime

from .config import AppConfig
from .data import download_daily_batched
from .models import SetupState
from .scanner import scan_symbol
from .universe import fetch_liquid_market_metadata, fetch_us_equity_universe


def run_market_scan(cfg: AppConfig, limit: int | None = None, on_batch=None) -> dict:
    """Build, liquidity-filter, scan, rank, then diversify the US universe."""
    official = {entry.symbol for entry in fetch_us_equity_universe(cfg.universe)}
    metadata = fetch_liquid_market_metadata(cfg.universe)
    symbols = [symbol for symbol in metadata if symbol in official][:limit]
    data = download_daily_batched(symbols + [cfg.benchmark], batch_size=cfg.universe.batch_size, on_batch=on_batch)
    if cfg.benchmark not in data:
        raise RuntimeError(f"Benchmark {cfg.benchmark} data was not returned")
    leaders = []
    for symbol in symbols:
        if symbol not in data:
            continue
        try:
            result = scan_symbol(symbol, data[symbol], data[cfg.benchmark], cfg.scanner)
        except Exception:
            continue
        if result.setup_state != SetupState.NONE and result.score >= cfg.universe.watch_score_floor and not result.warnings:
            item = result.to_dict() | {key: metadata[symbol].get(key) for key in ("name", "sector", "industry", "market_cap")}
            leaders.append(item)
    leaders.sort(key=lambda item: (item["setup_state"] == "TRIGGERED", item["setup_state"] == "READY", item["score"]), reverse=True)

    recommendations, sector_counts, industry_counts = [], {}, {}
    for item in leaders:
        sector = item.get("sector") or "Unknown"
        industry = item.get("industry") or item["symbol"]
        if sector_counts.get(sector, 0) >= cfg.universe.max_recommendations_per_sector:
            continue
        if industry_counts.get(industry, 0) >= cfg.universe.max_recommendations_per_industry:
            continue
        recommendations.append(item)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if len(recommendations) >= cfg.universe.recommendation_count:
            break
    return {
        "as_of": datetime.now(UTC).isoformat(), "universe_size": len(symbols),
        "symbols_with_data": len(data) - 1, "raw_leaders": leaders[: cfg.universe.recommendation_count],
        "recommendations": recommendations,
    }

