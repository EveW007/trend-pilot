#!/usr/bin/env python3
"""Load local Kronos-small weights and run a deterministic-shape smoke test."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import torch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.repo.resolve()))
    from model import Kronos, KronosPredictor, KronosTokenizer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch.manual_seed(7)
    tokenizer = KronosTokenizer.from_pretrained(str(args.tokenizer.resolve()))
    model = Kronos.from_pretrained(str(args.model.resolve()))
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

    rng = np.random.default_rng(7)
    rows = 96
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, rows)))
    open_ = close * (1 + rng.normal(0, 0.002, rows))
    high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.008, rows))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.008, rows))
    volume = rng.integers(1_000_000, 5_000_000, rows).astype(float)
    history = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )
    x_timestamp = pd.Series(pd.bdate_range("2025-01-02", periods=rows))
    next_day = pd.Timestamp(x_timestamp.iloc[-1].date() + timedelta(days=1))
    y_timestamp = pd.Series(pd.bdate_range(next_day, periods=2))
    forecast = predictor.predict(
        df=history,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=2,
        T=0.6,
        top_p=0.9,
        sample_count=1,
        verbose=False,
    )
    numeric = forecast.select_dtypes(include=["number"])
    if len(forecast) != 2 or numeric.empty or not np.isfinite(numeric.to_numpy()).all():
        raise RuntimeError("Kronos smoke test returned invalid output")

    print(
        json.dumps(
            {
                "status": "ok",
                "device": device,
                "torch": torch.__version__,
                "rows": len(forecast),
                "columns": list(forecast.columns),
                "first_close": float(forecast.iloc[0]["close"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
