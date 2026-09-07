from __future__ import annotations

import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from .config import AccountConfig, ScannerConfig
from .models import OrderProposal, ProposalStatus, ScanResult


def research_position_plan(price: float, atr_value: float, capital: float, risk_pct: float = 0.0035, max_position_pct: float = 0.10) -> dict:
    """Return transparent sizing math; this function never places an order."""
    if min(price, atr_value, capital, risk_pct, max_position_pct) <= 0:
        raise ValueError("All inputs must be positive")
    stop = max(price - 2 * atr_value, price * 0.92)
    per_share_risk = price - stop
    shares = min(math.floor(capital * risk_pct / per_share_risk), math.floor(capital * max_position_pct / price))
    return {
        "entry": round(price, 2),
        "stop": round(stop, 2),
        "shares": max(shares, 0),
        "estimated_risk": round(max(shares, 0) * per_share_risk, 2),
        "note": "research only; human review required",
    }


def build_proposal(result: ScanResult, account: AccountConfig, scanner: ScannerConfig, ttl_minutes: int = 240) -> OrderProposal:
    if result.setup_state.value not in {"READY", "TRIGGERED"}:
        raise ValueError("Only READY or TRIGGERED setups can create proposals")
    if result.score < scanner.minimum_score or result.warnings:
        raise ValueError("Proposal blocked by score or liquidity warnings")
    trigger = max(result.pivot + 0.10 * result.atr, result.close if result.setup_state.value == "TRIGGERED" else 0)
    limit_price = trigger + min(0.35 * result.atr, trigger * 0.005)
    stop_loss = min(max(trigger - 2 * result.atr, trigger * 0.92), trigger * 0.98)
    per_share_risk = limit_price - stop_loss
    if per_share_risk <= 0:
        raise ValueError("Invalid stop geometry")
    quantity = min(
        math.floor(account.net_liquidation * account.risk_per_trade_pct / per_share_risk),
        math.floor(account.net_liquidation * account.max_position_pct / limit_price),
    )
    if quantity < 1:
        raise ValueError("Account limits produce a zero-share proposal")
    now = datetime.now(UTC)
    return OrderProposal(
        id=str(uuid.uuid4()), symbol=result.symbol, created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(), status=ProposalStatus.PENDING_APPROVAL,
        strategy="Stage 2 + VCP breakout", score=result.score, current_price=round(result.close, 2),
        trigger_price=round(trigger, 2), limit_price=round(limit_price, 2), stop_loss_price=round(stop_loss, 2),
        take_profit_price=round(limit_price + 2 * per_share_risk, 2), quantity=quantity,
        estimated_notional=round(quantity * limit_price, 2), estimated_risk=round(quantity * per_share_risk, 2),
        account_risk_pct=round(quantity * per_share_risk / account.net_liquidation, 6), rationale=[],
        warnings=["Earnings date not validated; human review required"], approval_token=secrets.token_urlsafe(24),
    )
