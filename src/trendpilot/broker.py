from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .config import BrokerConfig
from .models import OrderProposal


@dataclass(slots=True)
class SubmissionResult:
    accepted: bool
    broker_order_id: str
    message: str


class DryRunBroker:
    def submit_bracket(self, proposal: OrderProposal) -> SubmissionResult:
        return SubmissionResult(
            accepted=True,
            broker_order_id=f"DRY-{proposal.id[:8]}",
            message="Dry-run only: no order was sent to a broker.",
        )


class IBKRPaperBroker:
    PAPER_PORTS = {7497, 4002}

    def __init__(self, config: BrokerConfig):
        self.config = config
        if not config.paper_only:
            raise RuntimeError("This release supports IBKR Paper only")
        if config.live_trading_enabled:
            raise RuntimeError("Live trading is intentionally disabled")
        if config.port not in self.PAPER_PORTS:
            raise RuntimeError(f"Refusing non-paper IBKR port {config.port}")
        if config.account_id and not config.account_id.upper().startswith("DU"):
            raise RuntimeError("Paper-only mode requires an IBKR paper account beginning with DU")

    def submit_bracket(self, proposal: OrderProposal) -> SubmissionResult:
        try:
            from ibapi.client import EClient
            from ibapi.contract import Contract
            from ibapi.order import Order
            from ibapi.wrapper import EWrapper
        except ImportError as exc:
            raise RuntimeError("Install the IBKR extra: pip install -e '.[ibkr]'") from exc

        ready = threading.Event()

        class App(EWrapper, EClient):
            def __init__(self):
                EClient.__init__(self, self)
                self.next_id: int | None = None
                self.errors: list[str] = []

            def nextValidId(self, orderId: int):  # noqa: N802 - IBKR callback name
                self.next_id = orderId
                ready.set()

            def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):  # noqa: N802
                if int(errorCode) >= 1000:
                    self.errors.append(f"{errorCode}: {errorString}")

        app = App()
        app.connect(self.config.host, self.config.port, clientId=self.config.client_id)
        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()
        if not ready.wait(timeout=10) or app.next_id is None:
            app.disconnect()
            raise RuntimeError("IBKR connection did not provide a valid order ID")

        contract = Contract()
        contract.symbol = proposal.symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        parent_id = app.next_id
        parent = Order()
        parent.orderId = parent_id
        parent.action = "BUY"
        parent.orderType = "STP LMT"
        parent.totalQuantity = proposal.quantity
        parent.auxPrice = proposal.trigger_price
        parent.lmtPrice = proposal.limit_price
        parent.tif = "DAY"
        parent.account = self.config.account_id
        parent.transmit = False
        parent.orderRef = f"trendpilot:{proposal.id}"

        take_profit = Order()
        take_profit.orderId = parent_id + 1
        take_profit.action = "SELL"
        take_profit.orderType = "LMT"
        take_profit.totalQuantity = proposal.quantity
        take_profit.lmtPrice = proposal.take_profit_price
        take_profit.parentId = parent_id
        take_profit.account = self.config.account_id
        take_profit.transmit = False
        take_profit.orderRef = f"trendpilot:{proposal.id}:tp"

        stop_loss = Order()
        stop_loss.orderId = parent_id + 2
        stop_loss.action = "SELL"
        stop_loss.orderType = "STP"
        stop_loss.totalQuantity = proposal.quantity
        stop_loss.auxPrice = proposal.stop_loss_price
        stop_loss.parentId = parent_id
        stop_loss.account = self.config.account_id
        stop_loss.transmit = True
        stop_loss.orderRef = f"trendpilot:{proposal.id}:sl"

        app.placeOrder(parent.orderId, contract, parent)
        app.placeOrder(take_profit.orderId, contract, take_profit)
        app.placeOrder(stop_loss.orderId, contract, stop_loss)
        time.sleep(1.0)
        app.disconnect()
        if app.errors:
            return SubmissionResult(False, str(parent_id), "; ".join(app.errors))
        return SubmissionResult(True, str(parent_id), "Bracket submitted to IBKR Paper")

