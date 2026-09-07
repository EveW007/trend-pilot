from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class SetupState(StrEnum):
    NONE = "NONE"
    WATCH = "WATCH"
    READY = "READY"
    TRIGGERED = "TRIGGERED"


class ProposalStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"


@dataclass(slots=True)
class ScanResult:
    symbol: str
    as_of: str
    close: float
    stage2_passes: int
    stage2: bool
    momentum_5d: float
    momentum_20d: float
    momentum_63d: float
    relative_strength_63d: float
    box_low: float
    pivot: float
    box_width_pct: float
    volume_dry_up_ratio: float
    range_contraction_ratio: float
    distance_to_pivot_pct: float
    relative_volume: float
    atr: float
    setup_state: SetupState
    score: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        value = asdict(self)
        value["setup_state"] = self.setup_state.value
        return value


@dataclass(slots=True)
class OrderProposal:
    id: str
    symbol: str
    created_at: str
    expires_at: str
    status: ProposalStatus
    strategy: str
    score: float
    current_price: float
    trigger_price: float
    limit_price: float
    stop_loss_price: float
    take_profit_price: float
    quantity: int
    estimated_notional: float
    estimated_risk: float
    account_risk_pct: float
    rationale: list[str]
    warnings: list[str]
    approval_token: str
    approved_at: str | None = None
    submitted_at: str | None = None
    broker_order_id: str | None = None
    broker_message: str | None = None

    def to_dict(self, include_token: bool = False) -> dict:
        value = asdict(self)
        value["status"] = self.status.value
        if not include_token:
            value.pop("approval_token", None)
        return value


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
