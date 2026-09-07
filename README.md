# TrendPilot Lite

TrendPilot Lite is a compact, reproducible implementation of an established
Stage 2 / Minervini-style trend and volatility-contraction workflow. It ranks a
small list of liquid US stocks or ETFs using trend structure, 63-day relative
strength versus SPY, box width, range contraction, volume dry-up, pivot
proximity, and breakout volume.

This repository demonstrates my implementation choices and investment process;
it does **not** claim that the underlying Stage 2 or VCP concepts are original.

## What it does

- Applies eight transparent Stage 2 trend rules.
- Detects a 30-session box and a simple three-stage volatility contraction.
- Labels each setup `NONE`, `WATCH`, `READY`, or `TRIGGERED`.
- Rejects low-price and low-dollar-volume candidates.
- Produces a deterministic score and an ATR-based research risk plan.
- Builds a broad US-listed stock/ETF universe while filtering warrants, rights,
  preferred shares, test issues, and other non-common instruments.
- Includes an event-driven breakout backtest and optional VectorBT adapter.
- Persists proposals with expiring, one-time human approval tokens.
- Keeps a dry-run/Paper-only brokerage boundary; the public build omits the
  actual network submission method.
- Summarizes probabilistic Kronos paths as a secondary research layer without
  allowing the model to select securities or issue an order.

## What it deliberately does not do

- No live brokerage connection or automatic order submission.
- No live or tick-level market data; Yahoo Finance is used for an end-of-day demo.
- No downloaded model weights, proprietary datasets, cached prices, or reports.
- No claim that a score is investment advice or evidence of future returns.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
cp config.example.json config.json
trendpilot --config config.json
pytest
```

Useful commands:

```bash
trendpilot --config config.json scan
trendpilot --config config.json universe
trendpilot --config config.json market-scan --limit 300
trendpilot --config config.json backtest NVDA
trendpilot --config config.json scan --create-proposals
trendpilot --config config.json dashboard
trendpilot --config config.json list
trendpilot --config config.json watch --interval-seconds 900
```

Approval never submits an order. Paper submission is a separate command and
requires the literal `--ack SUBMIT-IBKR-PAPER`; the default broker mode is
`dry-run`. Live ports, live accounts, and live-trading flags are rejected.

The scanner prints JSON ranked by score. `TRIGGERED` requires a close no more
than 3% above the prior box pivot and relative volume of at least 1.5×. Any
position plan is informational and requires an independent human decision.

## Project layout

```text
trendpilot-lite/
├── src/trendpilot/     # scanner, universe, backtest, risk and approval logic
├── scripts/            # model-output summarization; no model weights
├── tests/              # deterministic synthetic-data tests
├── config.example.json
├── pyproject.toml
└── README.md
```

## Method notes

The implementation uses adjusted daily OHLCV data. The pivot is the highest
high in the previous 30 sessions, excluding the current bar. Relative volume is
the current session volume divided by the preceding 20-session mean. For an
unfinished intraday bar, that comparison is invalid unless volume is normalized
by elapsed trading time; this end-of-day version therefore uses complete daily
bars only.

## Limitations

The contraction detector is intentionally simple, earnings risk is not checked,
and public data can be delayed or revised. Before using the method in a real
portfolio, add licensed real-time data, event gates, slippage-aware backtesting,
portfolio-level exposure controls, and independent validation.
