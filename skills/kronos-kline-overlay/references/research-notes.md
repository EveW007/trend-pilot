# Kronos research notes

## Primary sources

- Paper: https://arxiv.org/abs/2508.02739
- AAAI 2026 version: https://ojs.aaai.org/index.php/AAAI/article/view/39730
- Official repository: https://github.com/shiyu-coder/Kronos
- Official checkpoints: https://huggingface.co/NeoQuasar

## What the paper proposes

Kronos models an OHLCVA bar as a discrete language token. A Transformer autoencoder and Binary Spherical Quantization encode every bar into a coarse and a fine subtoken. A decoder-only Transformer then predicts the next coarse subtoken and, conditionally, its fine residual. Sampling these tokens autoregressively produces multiple possible future K-line paths.

The pretraining corpus contains more than 12 billion bars from more than 45 exchanges at seven frequencies. The paper reports zero-shot price, return, and volatility forecasts, synthetic K-line generation, and an A-share investment simulation. Public model sizes include mini, small, and base; the reported 499.2M-parameter large model is not publicly released in the official model zoo as of the repository version reviewed on 2026-08-15.

## Results that matter

- Price-series RankIC improves 93% over the best tested general time-series foundation model and 87% over the best tested non-pretrained baseline. These are relative improvements on small IC values, not 93% directional accuracy.
- The A-share simulation uses daily bars, a 90-day lookback, a 10-day forecast, equal-weight top-k/drop-n portfolios, at least five days of holding, and 0.15% transaction cost per trade.
- Reported average annualized excess return is 17.89%, 18.89%, and 20.84% for small, base, and large respectively; corresponding average information ratios are 1.4222, 1.5217, and 1.6491.
- Pretraining ends in June 2024 and evaluation starts in July 2024. NASDAQ is included among the stock exchanges used in forecasting evaluation. The published investment simulation itself is on CSI 300/CSI 800, not US stocks.
- More inference samples improve stability in the paper. Directional forecasting favors lower temperature around 0.6; generation and volatility favor greater stochasticity.

## What the paper does not establish

- It does not validate a concentrated one-stock US swing strategy.
- It does not validate using a forecast to enter immediately before earnings or other binary events.
- It does not show that Kronos adds value beyond this project's existing box, volume, relative-strength, news, and portfolio gates.
- It does not eliminate regime change, data leakage, survivorship bias, corporate-action errors, or execution costs.
- RankIC measures ranking/correlation, not a guaranteed hit rate or calibrated probability of profit.

## Code observations

The official repository exposes `KronosPredictor`, accepting open/high/low/close with optional volume and amount. Public small/base models have a 512-token maximum context; the predictor truncates longer contexts. The fine-tuning example uses Qlib and explicitly calls itself a demonstration rather than a production trading system. Its backtest code delays execution and models open/close costs, but production use still needs point-in-time universes, US market conventions, slippage, spread, and event controls.

The repository uses the MIT license. Pin a commit and preserve its license if code is vendored or modified.
