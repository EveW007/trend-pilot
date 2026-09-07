# TrendPilot

TrendPilot is a human-approved research and paper-trading system for finding short-term momentum setups in liquid US equities and ETFs. It combines Stage 2 / Minervini-style trend filters, relative strength, volatility contraction, box breakouts, liquidity controls, deterministic position sizing, event-driven backtesting, and an optional Kronos forecasting overlay.

The project implements and integrates established trend-following concepts; it does not claim that Stage 2 or VCP methodology is original. This is a research system, not investment advice, and this release intentionally does **not** support live brokerage submission.

## System overview

```text
US-listed universe
  → instrument and liquidity filters
  → Stage 2 + relative strength + VCP/box analysis
  → ranked NONE / WATCH / READY / TRIGGERED candidates
  → backtest and optional Kronos secondary overlay
  → deterministic risk-sized proposal
  → expiring, one-time human approval
  → dry run or IBKR Paper only
```

## What is implemented

### Market universe and data pipeline

- Builds a current US-listed universe from Nasdaq Trader symbol directories.
- Filters test issues, warrants, rights, preferred shares, units, debt-like instruments, and other unsuitable listings.
- Supports configurable ETF and ADR inclusion.
- Applies market-cap and liquidity gates before downloading historical bars.
- Downloads adjusted daily OHLCV data in batches and tolerates failed batches.
- Produces raw leaders and sector/industry-capped recommendations.

### Trend and setup classification

Each symbol is evaluated with:

- eight Stage 2 conditions based on the 50-, 150-, and 200-day moving averages, 52-week range position, and 63-day performance versus SPY;
- a configurable 30-session box and prior-bar pivot;
- three-segment range contraction and recent volume dry-up;
- ATR, pivot distance, current relative volume, price, and 20-day average dollar volume;
- deterministic scoring and `NONE`, `WATCH`, `READY`, or `TRIGGERED` states.

A setup becomes `READY` only when its trend, box, contraction, volume dry-up, and pivot-proximity conditions agree. A `TRIGGERED` breakout must also satisfy the configured relative-volume requirement.

### Backtesting and evaluation

The event backtester models a stop-limit entry above the detected pivot, a three-session entry window, an ATR-based protective stop, configurable maximum holding time, conservative gap handling, and non-overlapping trades. It reports trade count, win rate, average return, compounded return, and trade details. An optional VectorBT adapter supports larger parameter studies.

No performance claims or precomputed results are bundled with this repository.

### Risk and approval workflow

- Position size is capped by both per-trade risk and maximum position exposure.
- Proposals contain trigger, limit, stop-loss, take-profit, quantity, estimated notional, and estimated risk.
- Only `READY` or `TRIGGERED` setups above the minimum score can create a proposal; liquidity warnings block creation.
- Proposals are stored locally in SQLite with unique approval tokens.
- Approval expires and can be exercised only once.
- The local dashboard changes proposal state only—it never submits an order.

### Broker safety boundary

1. Scanning can create a proposal but cannot approve or submit it.
2. A human must approve the proposal separately.
3. Submission requires the literal acknowledgement `SUBMIT-IBKR-PAPER`.
4. The IBKR adapter accepts Paper ports only: `7497` or `4002`.
5. The configured Paper account must begin with `DU`.
6. Live-trading flags and non-Paper configurations are rejected.
7. The default broker is a dry run and makes no broker call.

### Optional Kronos overlay

Kronos is an experimental secondary confirmation layer for a small shortlist. It cannot select the universe, change a failed setup to `TRIGGERED`, size a position, approve a proposal, or submit an order.

The repository keeps the integration contract, inference smoke test, pinned source/model revisions, and probabilistic path summarizer. Model weights and vendored upstream source are excluded because they are reproducible downloads. See the [integration contract](skills/kronos-kline-overlay/references/integration-contract.md).

## Repository layout

```text
src/trendpilot/
  scanner.py       Stage 2, VCP/box, liquidity, scoring and setup states
  universe.py      Listed-universe construction and metadata filtering
  data.py          Batched daily OHLCV download
  backtest.py      Event-driven backtest and optional VectorBT adapter
  risk.py          Proposal geometry and risk-based position sizing
  models.py        Scan, proposal and state models
  store.py         SQLite persistence and one-time approval logic
  broker.py        Dry-run and IBKR Paper bracket-order boundary
  dashboard.py     Local human-approval interface
  cli.py           End-to-end command-line workflow
  config.py        Typed configuration
scripts/           Reproducible Kronos download and smoke-test utilities
skills/            Kronos overlay contract, notes and path summarizer
tests/             Scanner, universe, risk, approval and broker safety tests
```

Generated data, reports, databases, model weights, virtual environments, credentials, caches, and third-party vendored source are excluded from Git.

## Installation

Requires Python 3.11 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e '.[dev]'
cp config.example.json config.json
pytest
```

Optional research and Paper broker integrations:

```bash
python3 -m pip install -e '.[research]'
python3 -m pip install -e '.[ibkr]'
```

`config.json` is ignored. Review the copied values—especially account size, risk limits, watchlist, and broker mode—before running the workflow. The example IBKR account value is a placeholder, not a usable credential.

## Usage

Build the listed universe:

```bash
trendpilot --config config.json universe
```

Run a broad market scan and write `data/latest_recommendations.json`:

```bash
trendpilot --config config.json market-scan
```

Scan the configured watchlist and optionally create proposals for qualifying triggered setups:

```bash
trendpilot --config config.json scan
trendpilot --config config.json scan --create-proposals
```

Run an event backtest:

```bash
trendpilot --config config.json backtest META --years 8
```

Start the local approval dashboard:

```bash
trendpilot --config config.json dashboard
```

Open `http://127.0.0.1:8765`. Approving a proposal does not send an order.

Monitor READY/TRIGGERED names generated by the broad scan:

```bash
trendpilot --config config.json watch --interval-seconds 900
```

List proposals and perform a dry submission after manual approval:

```bash
trendpilot --config config.json list
trendpilot --config config.json submit PROPOSAL_ID --ack SUBMIT-IBKR-PAPER
```

The default `broker.mode` is `dry-run`. To test IBKR Paper, install the `ibkr` extra, start TWS Paper or IB Gateway Paper with API access, configure the Paper account and Paper port, then set `broker.mode` to `ibkr-paper`.

## Reproducing the Kronos environment

`kronos.lock.json` records the upstream Kronos commit and immutable Hugging Face model revisions. Clone the recorded upstream commit separately, then download the pinned model snapshots:

```bash
python scripts/download_kronos_models.py --output models/kronos
```

Run the inference smoke test with explicit repository and weight paths:

```bash
python scripts/smoke_test_kronos.py \
  --repo third_party/Kronos \
  --model models/kronos/Kronos-small \
  --tokenizer models/kronos/Kronos-Tokenizer-base
```

These directories remain ignored and must not be committed.

## Current limitations

- Yahoo Finance is suitable for this MVP and Paper research, not production execution or reliable real-time monitoring.
- The watch loop uses daily data; a short polling interval does not make it an intraday feed.
- Earnings-calendar validation is not implemented. Proposals therefore display an event-risk warning, and live trading remains disabled.
- The backtest uses daily bars and cannot reproduce tick-level ordering, partial fills, queue priority, or every gap behavior.
- Account reconciliation, portfolio heat enforcement, alert delivery, reconnect recovery, and broker-quality market-data validation are required before production deployment.

## Disclaimer

This software is provided for research and educational use. It does not provide investment advice, guarantee performance, or authorize unattended trading. Users are responsible for independently validating data, assumptions, risk, regulatory requirements, and every trading decision.
