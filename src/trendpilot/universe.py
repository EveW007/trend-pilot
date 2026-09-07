from __future__ import annotations

import csv
import io
import json
import re
import ssl
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import UniverseConfig


NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NASDAQ_SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit={limit}&offset={offset}"
NASDAQ_SCREENER_FULL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0&download=true"


@dataclass(slots=True)
class UniverseEntry:
    symbol: str
    name: str
    exchange: str
    is_etf: bool
    is_adr: bool


def _download_text(url: str, timeout: int = 30) -> str:
    try:
        from curl_cffi import requests as curl_requests

        response = curl_requests.get(url, impersonate="chrome", timeout=timeout)
        response.raise_for_status()
        return response.text
    except ImportError:
        pass
    request = urllib.request.Request(url, headers={"User-Agent": "TrendPilot/0.1 research@example.invalid"})
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return response.read().decode("utf-8", errors="replace")


def _is_common_equity(name: str) -> bool:
    lowered = name.lower()
    blocked = (
        "warrant",
        "rights",
        " units",
        "unit exp",
        "preferred",
        "depositary shares each representing",
        "beneficial interest",
        "notes due",
        "debenture",
        "income shares",
    )
    return not any(term in lowered for term in blocked)


def _yahoo_symbol(symbol: str) -> str:
    # Yahoo uses a dash for US class-share separators (BRK.B -> BRK-B).
    return symbol.replace(".", "-").replace("$", "-")


def _parse_nasdaq(text: str, cfg: UniverseConfig) -> list[UniverseEntry]:
    rows = csv.DictReader(io.StringIO(text), delimiter="|")
    entries: list[UniverseEntry] = []
    for row in rows:
        symbol = (row.get("Symbol") or "").strip()
        name = (row.get("Security Name") or "").strip()
        if not symbol or symbol.startswith("File Creation Time"):
            continue
        if row.get("Test Issue") == "Y" or row.get("Financial Status", "N") not in {"", "N"}:
            continue
        is_etf = row.get("ETF", "N") == "Y"
        is_adr = "depositary" in name.lower() or "adr" in name.lower()
        if (is_etf and not cfg.include_etfs) or (is_adr and not cfg.include_adrs):
            continue
        if not _is_common_equity(name) or not re.fullmatch(r"[A-Z][A-Z0-9.\-$]{0,13}", symbol):
            continue
        entries.append(UniverseEntry(_yahoo_symbol(symbol), name, "NASDAQ", is_etf, is_adr))
    return entries


def _parse_other(text: str, cfg: UniverseConfig) -> list[UniverseEntry]:
    rows = csv.DictReader(io.StringIO(text), delimiter="|")
    exchange_names = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "Cboe", "V": "IEX"}
    entries: list[UniverseEntry] = []
    for row in rows:
        symbol = (row.get("ACT Symbol") or "").strip()
        name = (row.get("Security Name") or "").strip()
        if not symbol or symbol.startswith("File Creation Time") or row.get("Test Issue") == "Y":
            continue
        is_etf = row.get("ETF", "N") == "Y"
        is_adr = "depositary" in name.lower() or "adr" in name.lower()
        if (is_etf and not cfg.include_etfs) or (is_adr and not cfg.include_adrs):
            continue
        if not _is_common_equity(name) or not re.fullmatch(r"[A-Z][A-Z0-9.\-$]{0,13}", symbol):
            continue
        entries.append(
            UniverseEntry(_yahoo_symbol(symbol), name, exchange_names.get(row.get("Exchange", ""), "OTHER"), is_etf, is_adr)
        )
    return entries


def fetch_us_equity_universe(cfg: UniverseConfig) -> list[UniverseEntry]:
    entries = _parse_nasdaq(_download_text(NASDAQ_LISTED), cfg) + _parse_other(_download_text(OTHER_LISTED), cfg)
    unique = {entry.symbol: entry for entry in entries}
    return sorted(unique.values(), key=lambda entry: entry.symbol)


def fetch_liquid_market_metadata(cfg: UniverseConfig) -> dict[str, dict]:
    """Return a broad, liquid subset using Nasdaq.com's current stock screener.

    The official symbol directories remain the source of truth for listed issues;
    this endpoint only reduces the expensive historical-data download set.
    """
    rows: list[dict] = []
    try:
        raw = json.loads(_download_text(NASDAQ_SCREENER_FULL, timeout=90))
        rows = (((raw or {}).get("data") or {}).get("rows") or [])
    except Exception:
        page_size = 1000
        for offset in range(0, 10_000, page_size):
            url = NASDAQ_SCREENER.format(limit=page_size, offset=offset)
            raw = json.loads(_download_text(url, timeout=75))
            data_block = (raw or {}).get("data") or {}
            page = ((data_block.get("table") or {}).get("rows") or data_block.get("rows") or [])
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
    selected: list[dict] = []
    for row in rows:
        symbol = _yahoo_symbol(str(row.get("symbol") or "").upper())
        try:
            price = float(str(row.get("lastsale") or "0").replace("$", "").replace(",", ""))
            volume = float(str(row.get("volume") or "0").replace(",", ""))
            market_cap = float(str(row.get("marketCap") or "0").replace(",", ""))
        except ValueError:
            continue
        industry = str(row.get("industry") or "")
        if market_cap < cfg.minimum_market_cap or price <= 0:
            continue
        # Nasdaq's paginated response currently omits volume, while its full
        # export includes it. Apply the volume gate when present; otherwise
        # retain the large-cap issue and let 20-day OHLCV enforce liquidity.
        if volume > 0 and price * volume < cfg.minimum_session_dollar_volume:
            continue
        if "blank checks" in industry.lower():
            continue
        selected.append(
            {
                "symbol": symbol,
                "name": str(row.get("name") or symbol),
                "sector": str(row.get("sector") or ""),
                "industry": industry,
                "price": price,
                "session_volume": volume,
                "market_cap": market_cap,
                "session_dollar_volume": price * volume,
                "liquidity_rank": price * volume if volume > 0 else market_cap,
            }
        )
    selected.sort(key=lambda item: item["liquidity_rank"], reverse=True)
    return {item["symbol"]: item for item in selected[: cfg.max_liquid_symbols]}


def save_universe(entries: list[UniverseEntry], path: str = "data/universe.json") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "count": len(entries),
        "entries": [asdict(entry) for entry in entries],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
