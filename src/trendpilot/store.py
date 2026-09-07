from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .models import OrderProposal, ProposalStatus


class ProposalStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, symbol TEXT NOT NULL, status TEXT NOT NULL, approval_token TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, proposal: OrderProposal) -> None:
        payload = json.dumps(proposal.to_dict(include_token=True))
        with self._connect() as conn:
            conn.execute("INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload, updated_at=excluded.updated_at", (proposal.id, proposal.symbol, proposal.status.value, proposal.approval_token, proposal.expires_at, payload, datetime.now(UTC).isoformat()))

    @staticmethod
    def _from_row(row: sqlite3.Row) -> OrderProposal:
        raw = json.loads(row["payload"])
        raw["status"] = ProposalStatus(raw["status"])
        return OrderProposal(**raw)

    def get_by_token(self, token: str) -> OrderProposal | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE approval_token = ?", (token,)).fetchone()
        return self._from_row(row) if row else None

    def get(self, proposal_id: str) -> OrderProposal | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[OrderProposal]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM proposals ORDER BY updated_at DESC").fetchall()
        return [self._from_row(row) for row in rows]

    def has_active_for_symbol(self, symbol: str) -> bool:
        active = {ProposalStatus.PENDING_APPROVAL, ProposalStatus.APPROVED, ProposalStatus.SUBMITTED}
        now = datetime.now(UTC)
        return any(proposal.symbol == symbol.upper() and proposal.status in active and datetime.fromisoformat(proposal.expires_at) > now for proposal in self.list())

    def decide(self, token: str, approve: bool) -> OrderProposal:
        proposal = self.get_by_token(token)
        if not proposal:
            raise ValueError("Unknown approval token")
        if proposal.status != ProposalStatus.PENDING_APPROVAL:
            raise ValueError(f"Proposal is already {proposal.status.value}")
        if datetime.fromisoformat(proposal.expires_at) <= datetime.now(UTC):
            proposal.status = ProposalStatus.EXPIRED
            self.save(proposal)
            raise ValueError("Proposal has expired")
        proposal.status = ProposalStatus.APPROVED if approve else ProposalStatus.REJECTED
        proposal.approved_at = datetime.now(UTC).isoformat() if approve else None
        self.save(proposal)
        return proposal
