# TrendPilot integration contract

## Role in the pipeline

Use this order:

1. Broad liquid-US-equity universe scan.
2. Stage-2 trend, box/VCP, relative strength, liquidity, and relative-volume gates.
3. Company event, earnings-calendar, sector-coherence, and portfolio-overlap checks.
4. Kronos multi-path overlay for no more than the top 5-15 survivors.
5. Risk-based proposal construction.
6. Human approval.

Kronos is not a universe scanner and must not bypass steps 1-3 or 5-6.

## Initial research configurations

Use configurations derived from the paper as starting hypotheses, not optimized production settings:

- Swing, roughly 2-12 trading days: completed daily bars, 90-bar lookback, 10-bar horizon, at least 20 samples.
- Short swing, roughly 1-3 trading days: completed hourly bars, 80-bar lookback, 12-bar horizon, at least 20 samples.
- Start directional experiments near temperature 0.6. Record top-p and test sensitivity rather than silently choosing the best hindsight setting.

Use split/dividend-adjusted price bars consistently. Keep raw volume unless the data vendor's adjustment is documented. Omit amount if the US data source cannot provide a consistent turnover field.

## Forecast payload

Pass `scripts/summarize_paths.py` JSON shaped as:

```json
{
  "symbol": "NVDA",
  "as_of": "2026-08-14T20:00:00Z",
  "current_close": 225.16,
  "pivot": 232.00,
  "invalidation": 216.00,
  "paths": [
    {"close": [226.0, 229.0, 233.0], "low": [222.0, 225.0, 228.0]},
    {"close": [224.0, 221.0, 218.0], "low": [220.0, 217.0, 214.0]}
  ]
}
```

The script summarizes forecasts but does not make a trade decision. Overlay labels must be assigned by the calling workflow using pre-registered thresholds validated out of sample.

## Storage fields

Store the overlay beside, not inside, the existing scanner score:

- `kronos_status`: `EXPERIMENTAL`, `VALIDATED`, or `UNAVAILABLE`
- `kronos_overlay`: `CONFIRM`, `NEUTRAL`, `CONTRADICT`, or `UNAVAILABLE`
- `kronos_model`, `kronos_tokenizer`, `kronos_commit`
- `bar_frequency`, `lookback`, `horizon`, `sample_count`, `temperature`, `top_p`
- all distribution metrics emitted by the summarizer
- `data_as_of`, `generated_at`, and `validation_version`

Never mutate `setup_state` from `WATCH` or failed to `TRIGGERED` because of Kronos. A proposal remains impossible without the existing price/volume trigger and manual approval.
