from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from dataclasses import dataclass

from .config import UniverseConfig


NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NASDAQ_SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0&download=true"


@dataclass(slots=True)
class UniverseEntry:
    symbol: str
    name: str
    exchange: str
    is_etf: bool
    is_adr: bool


def _download_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "TrendPilot research@example.invalid"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _is_common_equity(name: str) -> bool:
    blocked = ("warrant", "rights", " units", "preferred", "notes due", "debenture", "blank check")
    return not any(term in name.lower() for term in blocked)


def _yahoo_symbol(symbol: str) -> str:
    return symbol.replace(".", "-").replace("$", "-")


def _valid(symbol: str, name: str, is_etf: bool, is_adr: bool, cfg: UniverseConfig) -> bool:
    return bool(symbol and re.fullmatch(r"[A-Z][A-Z0-9.\-$]{0,13}", symbol) and _is_common_equity(name) and (cfg.include_etfs or not is_etf) and (cfg.include_adrs or not is_adr))


def _parse_nasdaq(text: str, cfg: UniverseConfig) -> list[UniverseEntry]:
    entries = []
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        symbol, name = (row.get("Symbol") or "").strip(), (row.get("Security Name") or "").strip()
        is_etf = row.get("ETF", "N") == "Y"
        is_adr = "depositary" in name.lower() or "adr" in name.lower()
        if row.get("Test Issue") != "Y" and row.get("Financial Status", "N") in {"", "N"} and _valid(symbol, name, is_etf, is_adr, cfg):
            entries.append(UniverseEntry(_yahoo_symbol(symbol), name, "NASDAQ", is_etf, is_adr))
    return entries


def _parse_other(text: str, cfg: UniverseConfig) -> list[UniverseEntry]:
    exchanges = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "Cboe", "V": "IEX"}
    entries = []
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        symbol, name = (row.get("ACT Symbol") or "").strip(), (row.get("Security Name") or "").strip()
        is_etf = row.get("ETF", "N") == "Y"
        is_adr = "depositary" in name.lower() or "adr" in name.lower()
        if row.get("Test Issue") != "Y" and _valid(symbol, name, is_etf, is_adr, cfg):
            entries.append(UniverseEntry(_yahoo_symbol(symbol), name, exchanges.get(row.get("Exchange", ""), "OTHER"), is_etf, is_adr))
    return entries


def fetch_us_equity_universe(cfg: UniverseConfig) -> list[UniverseEntry]:
    entries = _parse_nasdaq(_download_text(NASDAQ_LISTED), cfg) + _parse_other(_download_text(OTHER_LISTED), cfg)
    return sorted({entry.symbol: entry for entry in entries}.values(), key=lambda entry: entry.symbol)


def fetch_liquid_market_metadata(cfg: UniverseConfig) -> dict[str, dict]:
    raw = json.loads(_download_text(NASDAQ_SCREENER, timeout=90))
    rows = (((raw or {}).get("data") or {}).get("rows") or [])
    selected = []
    for row in rows:
        symbol = _yahoo_symbol(str(row.get("symbol") or "").upper())
        try:
            price = float(str(row.get("lastsale") or "0").replace("$", "").replace(",", ""))
            volume = float(str(row.get("volume") or "0").replace(",", ""))
            market_cap = float(str(row.get("marketCap") or "0").replace(",", ""))
        except ValueError:
            continue
        industry = str(row.get("industry") or "")
        if market_cap < cfg.minimum_market_cap or price < 10 or "blank checks" in industry.lower():
            continue
        if volume > 0 and price * volume < cfg.minimum_session_dollar_volume:
            continue
        selected.append({
            "symbol": symbol, "name": str(row.get("name") or symbol),
            "sector": str(row.get("sector") or ""), "industry": industry,
            "market_cap": market_cap, "liquidity_rank": price * volume if volume else market_cap,
        })
    selected.sort(key=lambda item: item["liquidity_rank"], reverse=True)
    return {item["symbol"]: item for item in selected[: cfg.max_liquid_symbols]}
