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
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approval_token TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, proposal: OrderProposal) -> None:
        payload = json.dumps(proposal.to_dict(include_token=True), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO proposals(id, symbol, status, approval_token, expires_at, payload, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    proposal.id,
                    proposal.symbol,
                    proposal.status.value,
                    proposal.approval_token,
                    proposal.expires_at,
                    payload,
                    datetime.now(UTC).isoformat(),
                ),
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> OrderProposal:
        raw = json.loads(row["payload"])
        raw["status"] = ProposalStatus(raw["status"])
        return OrderProposal(**raw)

    def get(self, proposal_id: str) -> OrderProposal | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        return self._from_row(row) if row else None

    def get_by_token(self, token: str) -> OrderProposal | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE approval_token = ?", (token,)).fetchone()
        return self._from_row(row) if row else None

    def list(self, statuses: set[ProposalStatus] | None = None) -> list[OrderProposal]:
        query = "SELECT * FROM proposals"
        args: tuple[str, ...] = ()
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            args = tuple(x.value for x in statuses)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._from_row(row) for row in rows]

    def has_active_for_symbol(self, symbol: str) -> bool:
        active = {ProposalStatus.PENDING_APPROVAL, ProposalStatus.APPROVED, ProposalStatus.SUBMITTED}
        now = datetime.now(UTC)
        for proposal in self.list(active):
            if proposal.symbol == symbol.upper() and datetime.fromisoformat(proposal.expires_at) > now:
                return True
        return False

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
        if approve:
            proposal.approved_at = datetime.now(UTC).isoformat()
        self.save(proposal)
        return proposal
