from __future__ import annotations

from trendpilot.config import AccountConfig, ScannerConfig
from trendpilot.broker import DryRunBroker
from trendpilot.models import ProposalStatus, ScanResult, SetupState
from trendpilot.risk import build_proposal
from trendpilot.store import ProposalStore


def ready_result() -> ScanResult:
    return ScanResult(
        symbol="MU",
        as_of="2026-08-13",
        close=128.0,
        stage2_passes=8,
        stage2_total=8,
        stage2=True,
        relative_strength_63d=0.2,
        box_width_pct=0.1,
        volume_dry_up_ratio=0.7,
        range_contraction_ratio=0.5,
        pivot=129.0,
        distance_to_pivot_pct=-0.00775,
        relative_volume=1.0,
        atr=3.0,
        setup_state=SetupState.READY,
        score=85,
        reasons=["测试信号"],
        warnings=[],
    )


def test_risk_sizing_and_manual_approval(tmp_path):
    proposal = build_proposal(ready_result(), AccountConfig(), ScannerConfig())
    assert proposal.quantity > 0
    assert proposal.estimated_risk <= 350.01
    assert proposal.trigger_price > 129
    store = ProposalStore(str(tmp_path / "proposals.sqlite3"))
    store.save(proposal)
    approved = store.decide(proposal.approval_token, approve=True)
    assert approved.status == ProposalStatus.APPROVED


def test_decision_is_one_time(tmp_path):
    proposal = build_proposal(ready_result(), AccountConfig(), ScannerConfig())
    store = ProposalStore(str(tmp_path / "proposals.sqlite3"))
    store.save(proposal)
    store.decide(proposal.approval_token, approve=False)
    try:
        store.decide(proposal.approval_token, approve=True)
    except ValueError as exc:
        assert "already" in str(exc)
    else:
        raise AssertionError("Second decision should fail")


def test_dry_run_never_reaches_broker():
    proposal = build_proposal(ready_result(), AccountConfig(), ScannerConfig())
    result = DryRunBroker().submit_bracket(proposal)
    assert result.accepted
    assert result.broker_order_id.startswith("DRY-")
    assert "no order" in result.message
