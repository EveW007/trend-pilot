from __future__ import annotations

import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from .config import AccountConfig, ScannerConfig
from .models import OrderProposal, ProposalStatus, ScanResult


def _round_price(value: float) -> float:
    return round(value + 1e-10, 2)


def build_proposal(
    result: ScanResult,
    account: AccountConfig,
    scanner: ScannerConfig,
    ttl_minutes: int = 240,
) -> OrderProposal:
    if result.setup_state.value not in {"READY", "TRIGGERED"}:
        raise ValueError("Only READY or TRIGGERED setups can create proposals")
    if result.score < scanner.minimum_score:
        raise ValueError(f"Score {result.score} is below minimum {scanner.minimum_score}")
    if result.warnings:
        raise ValueError("Proposal blocked by liquidity warnings")

    trigger = max(result.pivot + 0.10 * result.atr, result.close if result.setup_state.value == "TRIGGERED" else 0)
    limit_price = trigger + min(0.35 * result.atr, trigger * 0.005)
    raw_stop = trigger - 2.0 * result.atr
    min_stop = trigger * (1 - 0.08)
    max_stop = trigger * (1 - 0.02)
    stop_loss = min(max(raw_stop, min_stop), max_stop)
    per_share_risk = limit_price - stop_loss
    if per_share_risk <= 0:
        raise ValueError("Invalid stop geometry")

    risk_budget = account.net_liquidation * account.risk_per_trade_pct
    risk_quantity = math.floor(risk_budget / per_share_risk)
    notional_quantity = math.floor(account.net_liquidation * account.max_position_pct / limit_price)
    quantity = min(risk_quantity, notional_quantity)
    if quantity < 1:
        raise ValueError("Account limits produce a zero-share proposal")
    estimated_risk = quantity * per_share_risk
    take_profit = limit_price + 2.0 * per_share_risk
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=ttl_minutes)
    warnings = list(result.warnings)
    warnings.append("尚未核验下一次财报日期；Paper阶段允许，实盘阶段必须阻断")

    return OrderProposal(
        id=str(uuid.uuid4()),
        symbol=result.symbol,
        created_at=now.isoformat(),
        expires_at=expires.isoformat(),
        status=ProposalStatus.PENDING_APPROVAL,
        strategy="Stage 2 + VCP breakout",
        score=result.score,
        current_price=_round_price(result.close),
        trigger_price=_round_price(trigger),
        limit_price=_round_price(limit_price),
        stop_loss_price=_round_price(stop_loss),
        take_profit_price=_round_price(take_profit),
        quantity=quantity,
        estimated_notional=_round_price(quantity * limit_price),
        estimated_risk=_round_price(estimated_risk),
        account_risk_pct=round(estimated_risk / account.net_liquidation, 6),
        rationale=result.reasons,
        warnings=warnings,
        approval_token=secrets.token_urlsafe(24),
    )

