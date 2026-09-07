from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .backtest import run_event_backtest, summarize
from .broker import DryRunBroker, IBKRPaperBroker
from .config import load_config
from .dashboard import serve_dashboard
from .data import download_daily
from .data import download_daily_batched
from .models import ProposalStatus, SetupState
from .risk import build_proposal
from .scanner import scan_symbol
from .store import ProposalStore
from .universe import fetch_liquid_market_metadata, fetch_us_equity_universe, save_universe


def _json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _focused_symbols(cfg, recommendations_file: str | None) -> list[str]:
    if not recommendations_file:
        return cfg.watchlist
    path = Path(recommendations_file)
    if not path.exists():
        return cfg.watchlist
    payload = json.loads(path.read_text(encoding="utf-8"))
    symbols = [
        item["symbol"]
        for item in payload.get("recommendations", [])
        if item.get("setup_state") in {SetupState.READY.value, SetupState.TRIGGERED.value}
    ]
    return symbols or cfg.watchlist


def _perform_scan(args) -> dict:
    cfg = load_config(args.config)
    symbols = _focused_symbols(cfg, getattr(args, "recommendations_file", None))
    data = download_daily(symbols + [cfg.benchmark])
    if cfg.benchmark not in data:
        return {"error": f"Benchmark {cfg.benchmark} data was not returned", "results": [], "proposals": []}
    benchmark = data[cfg.benchmark]
    store = ProposalStore(cfg.database_path)
    results = []
    proposals = []
    for symbol in symbols:
        if symbol not in data:
            results.append({"symbol": symbol, "error": "No data returned"})
            continue
        try:
            result = scan_symbol(symbol, data[symbol], benchmark, cfg.scanner)
            results.append(result.to_dict())
            if (
                args.create_proposals
                and result.setup_state == SetupState.TRIGGERED
                and not result.warnings
                and not store.has_active_for_symbol(symbol)
            ):
                proposal = build_proposal(result, cfg.account, cfg.scanner, args.ttl_minutes)
                store.save(proposal)
                proposals.append(proposal.to_dict())
        except Exception as exc:
            results.append({"symbol": symbol, "error": str(exc)})
    return {"results": sorted(results, key=lambda x: x.get("score", -1), reverse=True), "proposals": proposals}


def command_scan(args) -> None:
    _json(_perform_scan(args))


def command_watch(args) -> None:
    print("TrendPilot watch loop started. It can create proposals but cannot approve or submit them.")
    while True:
        try:
            output = _perform_scan(args)
            now = datetime.now(UTC).isoformat()
            leaders = [
                f"{item['symbol']}:{item.get('setup_state', 'ERROR')}:{item.get('score', 0)}"
                for item in output.get("results", [])[:5]
            ]
            print(f"[{now}] leaders={','.join(leaders)} new_proposals={len(output.get('proposals', []))}", flush=True)
        except Exception as exc:
            print(f"[{datetime.now(UTC).isoformat()}] scan failed: {exc}", flush=True)
        if args.once:
            return
        time.sleep(args.interval_seconds)


def command_backtest(args) -> None:
    cfg = load_config(args.config)
    data = download_daily([args.symbol.upper(), cfg.benchmark], years=args.years)
    trades = run_event_backtest(args.symbol.upper(), data[args.symbol.upper()], data[cfg.benchmark], cfg.scanner)
    _json(summarize(trades))


def command_universe(args) -> None:
    cfg = load_config(args.config)
    entries = fetch_us_equity_universe(cfg.universe)
    save_universe(entries, args.output)
    _json({"count": len(entries), "output": args.output, "sample": [entry.symbol for entry in entries[:20]]})


def command_market_scan(args) -> None:
    cfg = load_config(args.config)
    entries = fetch_us_equity_universe(cfg.universe)
    official_symbols = {entry.symbol for entry in entries}
    metadata = fetch_liquid_market_metadata(cfg.universe)
    liquid_symbols = [symbol for symbol in metadata if symbol in official_symbols]
    entries_by_symbol = {entry.symbol: entry for entry in entries}
    entries = [entries_by_symbol[symbol] for symbol in liquid_symbols]
    if args.limit:
        entries = entries[: args.limit]
    symbols = [entry.symbol for entry in entries]
    names = {entry.symbol: metadata.get(entry.symbol, {}).get("name", entry.name) for entry in entries}

    def progress(done, total, available, error):
        message = f"market data: {done}/{total}, usable={available}"
        if error:
            message += f", batch_error={error}"
        print(message, flush=True)

    data = download_daily_batched(
        symbols + [cfg.benchmark],
        years=2,
        batch_size=cfg.universe.batch_size,
        on_batch=progress,
    )
    if cfg.benchmark not in data:
        raise SystemExit(f"Benchmark {cfg.benchmark} data was not returned")
    results = []
    for symbol in symbols:
        frame = data.get(symbol)
        if frame is None:
            continue
        try:
            result = scan_symbol(symbol, frame, data[cfg.benchmark], cfg.scanner)
        except Exception:
            continue
        item = result.to_dict()
        item["name"] = names.get(symbol, symbol)
        item["sector"] = metadata.get(symbol, {}).get("sector", "")
        item["industry"] = metadata.get(symbol, {}).get("industry", "")
        item["market_cap"] = metadata.get(symbol, {}).get("market_cap")
        if (
            result.setup_state != SetupState.NONE
            and result.score >= cfg.universe.watch_score_floor
            and not result.warnings
        ):
            results.append(item)
    results.sort(key=lambda item: (item["setup_state"] == "TRIGGERED", item["setup_state"] == "READY", item["score"]), reverse=True)
    raw_leaders = results[: cfg.universe.recommendation_count]
    recommendations = []
    sector_counts: dict[str, int] = {}
    industry_counts: dict[str, int] = {}
    for item in results:
        sector = item.get("sector") or "Unknown"
        industry = item.get("industry") or item.get("name") or item["symbol"]
        if sector_counts.get(sector, 0) >= cfg.universe.max_recommendations_per_sector:
            continue
        if industry_counts.get(industry, 0) >= cfg.universe.max_recommendations_per_industry:
            continue
        recommendations.append(item)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if len(recommendations) >= cfg.universe.recommendation_count:
            break
    output = {
        "as_of": datetime.now(UTC).isoformat(),
        "universe_size": len(entries),
        "symbols_with_data": len(data) - 1,
        "raw_leaders": raw_leaders,
        "recommendations": recommendations,
    }
    target = args.output
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    _json(output)


def command_list(args) -> None:
    cfg = load_config(args.config)
    store = ProposalStore(cfg.database_path)
    _json([proposal.to_dict() for proposal in store.list()])


def command_decide(args) -> None:
    cfg = load_config(args.config)
    proposal = ProposalStore(cfg.database_path).decide(args.token, approve=args.decision == "approve")
    _json(proposal.to_dict())


def command_submit(args) -> None:
    if args.ack != "SUBMIT-IBKR-PAPER":
        raise SystemExit("Refusing submission: pass --ack SUBMIT-IBKR-PAPER")
    cfg = load_config(args.config)
    store = ProposalStore(cfg.database_path)
    proposal = store.get(args.proposal_id)
    if not proposal:
        raise SystemExit("Proposal not found")
    if proposal.status != ProposalStatus.APPROVED:
        raise SystemExit(f"Proposal status must be APPROVED, got {proposal.status.value}")
    if datetime.fromisoformat(proposal.expires_at) <= datetime.now(UTC):
        proposal.status = ProposalStatus.EXPIRED
        store.save(proposal)
        raise SystemExit("Proposal expired before submission")
    broker = DryRunBroker() if cfg.broker.mode == "dry-run" else IBKRPaperBroker(cfg.broker)
    result = broker.submit_bracket(proposal)
    proposal.status = ProposalStatus.SUBMITTED if result.accepted else ProposalStatus.FAILED
    proposal.submitted_at = datetime.now(UTC).isoformat()
    proposal.broker_order_id = result.broker_order_id
    proposal.broker_message = result.message
    store.save(proposal)
    _json(proposal.to_dict())


def command_dashboard(args) -> None:
    cfg = load_config(args.config)
    serve_dashboard(ProposalStore(cfg.database_path), args.host, args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Human-approved US equity VCP proposal engine")
    parser.add_argument("--config", default="config.json")
    sub = parser.add_subparsers(required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("--create-proposals", action="store_true")
    scan.add_argument("--ttl-minutes", type=int, default=240)
    scan.set_defaults(func=command_scan)

    watch = sub.add_parser("watch")
    watch.add_argument("--create-proposals", action="store_true", default=True)
    watch.add_argument("--ttl-minutes", type=int, default=240)
    watch.add_argument("--interval-seconds", type=int, default=900)
    watch.add_argument("--once", action="store_true")
    watch.add_argument("--recommendations-file", default="data/latest_recommendations.json")
    watch.set_defaults(func=command_watch)

    universe = sub.add_parser("universe")
    universe.add_argument("--output", default="data/universe.json")
    universe.set_defaults(func=command_universe)

    market_scan = sub.add_parser("market-scan")
    market_scan.add_argument("--limit", type=int)
    market_scan.add_argument("--output", default="data/latest_recommendations.json")
    market_scan.set_defaults(func=command_market_scan)

    backtest = sub.add_parser("backtest")
    backtest.add_argument("symbol")
    backtest.add_argument("--years", type=int, default=8)
    backtest.set_defaults(func=command_backtest)

    listing = sub.add_parser("list")
    listing.set_defaults(func=command_list)

    decide = sub.add_parser("decide")
    decide.add_argument("token")
    decide.add_argument("decision", choices=["approve", "reject"])
    decide.set_defaults(func=command_decide)

    submit = sub.add_parser("submit")
    submit.add_argument("proposal_id")
    submit.add_argument("--ack", required=True)
    submit.set_defaults(func=command_submit)

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.set_defaults(func=command_dashboard)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
