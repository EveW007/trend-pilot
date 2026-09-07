from __future__ import annotations

from trendpilot.broker import DryRunBroker, IBKRPaperBroker
from trendpilot.config import AccountConfig, BrokerConfig, ScannerConfig, UniverseConfig
from trendpilot.models import ScanResult, SetupState
from trendpilot.risk import build_proposal
from trendpilot.store import ProposalStore
from trendpilot.universe import _parse_nasdaq, _parse_other
from trendpilot.backtest import BacktestTrade, summarize


def ready_result() -> ScanResult:
    return ScanResult(
        symbol="MU", as_of="2026-08-13", close=128, stage2_passes=8, stage2=True,
        momentum_5d=0.02, momentum_20d=0.08, momentum_63d=0.20,
        relative_strength_63d=0.12, box_low=118, pivot=129, box_width_pct=0.09,
        volume_dry_up_ratio=0.7, range_contraction_ratio=0.5,
        distance_to_pivot_pct=-0.00775, relative_volume=1, atr=3,
        setup_state=SetupState.READY, score=85, warnings=[],
    )


def test_universe_filters_non_common_instruments():
    nasdaq = "Symbol|Security Name|Test Issue|Financial Status|ETF\nAAPL|Apple Inc. - Common Stock|N|N|N\nQQQ|ETF Trust|N|N|Y\nBADW|Bad Co Warrant|N|N|N\n"
    other = "ACT Symbol|Security Name|Exchange|ETF|Test Issue\nBRK.B|Berkshire Hathaway Class B|N|N|N\nSPY|SPDR ETF|P|Y|N\n"
    cfg = UniverseConfig(include_etfs=False)
    symbols = [entry.symbol for entry in _parse_nasdaq(nasdaq, cfg) + _parse_other(other, cfg)]
    assert symbols == ["AAPL", "BRK-B"]


def test_proposal_requires_one_time_human_decision(tmp_path):
    proposal = build_proposal(ready_result(), AccountConfig(), ScannerConfig())
    store = ProposalStore(str(tmp_path / "proposals.sqlite3"))
    store.save(proposal)
    assert store.decide(proposal.approval_token, approve=True).status.value == "APPROVED"
    try:
        store.decide(proposal.approval_token, approve=False)
    except ValueError as exc:
        assert "already" in str(exc)
    else:
        raise AssertionError("A second decision must fail")


def test_broker_boundary_is_dry_run_or_paper_only():
    proposal = build_proposal(ready_result(), AccountConfig(), ScannerConfig())
    assert "no order" in DryRunBroker().submit_bracket(proposal).message
    try:
        IBKRPaperBroker(BrokerConfig(port=7496, account_id=""))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Live configuration must be rejected")


def test_backtest_summary_compounds_returns():
    trades = [
        BacktestTrade("X", "1", "2", "3", 100, 110, 0.10, "time"),
        BacktestTrade("X", "4", "5", "6", 100, 90, -0.10, "stop"),
    ]
    result = summarize(trades)
    assert result["trades"] == 2
    assert result["win_rate"] == 0.5
    assert result["total_compounded_return"] == -0.01
