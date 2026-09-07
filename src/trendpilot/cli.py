from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from dataclasses import asdict

from .backtest import run_event_backtest, summarize
from .config import load_config
from .data import download_daily
from .scanner import scan_symbol
from .universe import fetch_us_equity_universe
from .pipeline import run_market_scan
from .broker import DryRunBroker, IBKRPaperBroker
from .dashboard import serve_dashboard
from .models import ProposalStatus, SetupState
from .risk import build_proposal
from .store import ProposalStore


def main() -> None:
    parser = argparse.ArgumentParser(description="End-of-day Stage 2 and VCP scanner")
    parser.add_argument("--config", default="config.json")
    sub = parser.add_subparsers(dest="command")
    scan = sub.add_parser("scan")
    scan.add_argument("--create-proposals", action="store_true")
    backtest = sub.add_parser("backtest")
    backtest.add_argument("symbol")
    sub.add_parser("universe")
    market = sub.add_parser("market-scan")
    market.add_argument("--limit", type=int)
    sub.add_parser("list")
    decide = sub.add_parser("decide")
    decide.add_argument("token")
    decide.add_argument("decision", choices=["approve", "reject"])
    submit = sub.add_parser("submit-paper")
    submit.add_argument("proposal_id")
    submit.add_argument("--ack", required=True)
    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    watch = sub.add_parser("watch")
    watch.add_argument("--interval-seconds", type=int, default=900)
    watch.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.command == "universe":
        print(json.dumps([asdict(entry) for entry in fetch_us_equity_universe(cfg.universe)], indent=2))
        return
    if args.command == "backtest":
        data = download_daily([args.symbol.upper(), cfg.benchmark], years=8)
        print(json.dumps(summarize(run_event_backtest(args.symbol.upper(), data[args.symbol.upper()], data[cfg.benchmark], cfg.scanner)), indent=2))
        return
    if args.command == "market-scan":
        print(json.dumps(run_market_scan(cfg, args.limit), ensure_ascii=False, indent=2))
        return
    store = ProposalStore(cfg.database_path)
    if args.command == "list":
        print(json.dumps([proposal.to_dict() for proposal in store.list()], indent=2))
        return
    if args.command == "decide":
        print(json.dumps(store.decide(args.token, args.decision == "approve").to_dict(), indent=2))
        return
    if args.command == "dashboard":
        serve_dashboard(store, args.host, args.port)
        return
    if args.command == "submit-paper":
        if args.ack != "SUBMIT-IBKR-PAPER":
            raise SystemExit("Refusing submission: pass --ack SUBMIT-IBKR-PAPER")
        proposal = store.get(args.proposal_id)
        if not proposal or proposal.status != ProposalStatus.APPROVED:
            raise SystemExit("Proposal must exist and be APPROVED")
        if datetime.fromisoformat(proposal.expires_at) <= datetime.now(UTC):
            raise SystemExit("Proposal has expired")
        broker = DryRunBroker() if cfg.broker.mode == "dry-run" else IBKRPaperBroker(cfg.broker)
        print(json.dumps(asdict(broker.submit_bracket(proposal)), indent=2))
        return
    if args.command == "watch":
        while True:
            data = download_daily(cfg.symbols + [cfg.benchmark])
            leaders = []
            for symbol in cfg.symbols:
                if symbol in data and cfg.benchmark in data:
                    result = scan_symbol(symbol, data[symbol], data[cfg.benchmark], cfg.scanner)
                    leaders.append(f"{symbol}:{result.setup_state.value}:{result.score}")
                    if result.setup_state == SetupState.TRIGGERED and not result.warnings and not store.has_active_for_symbol(symbol):
                        store.save(build_proposal(result, cfg.account, cfg.scanner))
            print(f"[{datetime.now(UTC).isoformat()}] {','.join(leaders)}", flush=True)
            if args.once:
                return
            time.sleep(args.interval_seconds)
    data = download_daily(cfg.symbols + [cfg.benchmark])
    if cfg.benchmark not in data:
        raise SystemExit(f"No benchmark data returned for {cfg.benchmark}")
    results = []
    for symbol in cfg.symbols:
        try:
            result = scan_symbol(symbol, data[symbol], data[cfg.benchmark], cfg.scanner)
            results.append(result.to_dict())
            if getattr(args, "create_proposals", False) and result.setup_state == SetupState.TRIGGERED and not result.warnings and not store.has_active_for_symbol(symbol):
                store.save(build_proposal(result, cfg.account, cfg.scanner))
        except Exception as exc:
            results.append({"symbol": symbol, "error": str(exc)})
    results.sort(key=lambda item: item.get("score", -1), reverse=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
