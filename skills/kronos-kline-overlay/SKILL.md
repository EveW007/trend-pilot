---
name: kronos-kline-overlay
description: Evaluate shortlisted liquid US stocks or ETFs with Tsinghua University's Kronos financial K-line foundation model as an experimental secondary confirmation layer. Use when a user asks for Kronos/K-line-model forecasts, AI confirmation of box breakouts or pullbacks, multi-path OHLCV scenario analysis, or integration of Kronos into an existing momentum/watchlist workflow. Never use Kronos alone to select the universe, size a position, approve a proposal, or submit an order.
---

# Kronos K-line Overlay

Use Kronos after a conventional scanner has produced a small candidate list. Treat its forecasts as probabilistic evidence, not a price target.

## Load the references

- Read `references/research-notes.md` before explaining the model or making claims about the paper.
- Read `references/integration-contract.md` before scoring live candidates or changing a trading workflow.

## Run the overlay

1. Confirm the data cutoff, market session, bar frequency, adjustment method, and forecast horizon. Never include a partially formed bar as a completed bar.
2. Require a shortlist from independent signals such as Stage-2 trend, box/VCP structure, relative strength, volume confirmation, liquidity, and event risk.
3. Use official Kronos code and matching tokenizer/model checkpoints. Prefer an immutable repository commit and record model, tokenizer, parameters, and data cutoff.
4. Generate multiple paths. Default to at least 20 paths for research; use lower temperature for directional forecasting and report sensitivity to sampling settings.
5. Convert paths into a distribution with `scripts/summarize_paths.py`. Report median expected path return, terminal-return quantiles, probability of finishing positive, probability of clearing the technical pivot, probability of touching the invalidation level, and forecast dispersion.
6. Return exactly one overlay label: `CONFIRM`, `NEUTRAL`, `CONTRADICT`, or `UNAVAILABLE`. Keep the original scanner state and score separate.
7. Present any action as `等待`, `小仓试探`, or `确认后提案`. Require explicit human confirmation for every proposal. Never place or approve an order.

## Decision discipline

- Let Kronos upgrade confidence only after the technical setup is independently valid.
- Let a strongly adverse forecast distribution downgrade a candidate to `等待`; never let Kronos rescue a failed breakout, weak volume, broken invalidation level, or imminent binary event.
- Do not add Kronos points directly to the existing scanner score until a US-equity walk-forward test demonstrates out-of-sample incremental value after costs.
- Keep earnings, filings, news, valuation, and portfolio concentration outside the model. They remain separate veto and sizing inputs.
- Do not quote a single sampled path as the forecast. Use distributions and disclose disagreement among paths.
- Label zero-shot US-equity results `EXPERIMENTAL` until calibrated on point-in-time Nasdaq/S&P universes with survivorship-safe data.

## Validation gate

Before production use, run a chronological walk-forward study with:

- point-in-time index membership and corporate-action-adjusted bars;
- no overlap between model calibration and evaluation periods;
- baselines of the existing scanner alone and scanner plus a simple momentum/volatility model;
- slippage, commissions, spread, delistings, and earnings gaps;
- results by market regime, sector, liquidity, horizon, and forecast timestamp;
- incremental hit rate, excess return, information ratio, drawdown, turnover, and calibration.

Promote the overlay only if it improves the pre-registered primary metric on untouched data and does not materially worsen drawdown. Otherwise keep it as research-only context.

## Output contract

For each symbol show:

- timestamp and completed-bar cutoff;
- existing setup state, pivot, relative volume, and invalidation;
- Kronos model/tokenizer, bar frequency, lookback, horizon, samples, temperature, and top-p;
- distribution metrics and overlay label;
- event/portfolio vetoes;
- one of `等待`, `小仓试探`, or `确认后提案`, explicitly subject to human approval.

If model weights, a compatible runtime, reliable OHLCV data, or enough completed bars are unavailable, return `UNAVAILABLE` rather than improvising a forecast.
