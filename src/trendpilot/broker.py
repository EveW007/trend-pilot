from __future__ import annotations

from dataclasses import dataclass
import threading
import time

from .config import BrokerConfig
from .models import OrderProposal


@dataclass(slots=True)
class SubmissionResult:
    accepted: bool
    broker_order_id: str
    message: str


class DryRunBroker:
    def submit_bracket(self, proposal: OrderProposal) -> SubmissionResult:
        return SubmissionResult(True, f"DRY-{proposal.id[:8]}", "Dry-run only: no order was sent to a broker.")


class IBKRPaperBroker:
    """Paper-only boundary. Live ports and non-paper accounts are rejected."""

    PAPER_PORTS = {7497, 4002}

    def __init__(self, config: BrokerConfig):
        self.config = config
        if not config.paper_only or config.live_trading_enabled:
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
                self.next_id = None
                self.errors = []

            def nextValidId(self, orderId):  # noqa: N802
                self.next_id = orderId
                ready.set()

            def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):  # noqa: N802
                if int(errorCode) >= 1000:
                    self.errors.append(f"{errorCode}: {errorString}")

        app = App()
        app.connect(self.config.host, self.config.port, clientId=self.config.client_id)
        threading.Thread(target=app.run, daemon=True).start()
        if not ready.wait(timeout=10) or app.next_id is None:
            app.disconnect()
            raise RuntimeError("IBKR connection did not provide a valid order ID")

        contract = Contract()
        contract.symbol, contract.secType, contract.exchange, contract.currency = proposal.symbol, "STK", "SMART", "USD"
        orders = []
        for offset, action, order_type, price, transmit in (
            (0, "BUY", "STP LMT", proposal.limit_price, False),
            (1, "SELL", "LMT", proposal.take_profit_price, False),
            (2, "SELL", "STP", proposal.stop_loss_price, True),
        ):
            order = Order()
            order.orderId, order.action, order.orderType = app.next_id + offset, action, order_type
            order.totalQuantity, order.account, order.transmit = proposal.quantity, self.config.account_id, transmit
            order.parentId = 0 if offset == 0 else app.next_id
            order.orderRef = f"trendpilot:{proposal.id}:{offset}"
            if order_type == "STP LMT":
                order.auxPrice, order.lmtPrice, order.tif = proposal.trigger_price, price, "DAY"
            elif order_type == "LMT":
                order.lmtPrice = price
            else:
                order.auxPrice = price
            orders.append(order)
        for order in orders:
            app.placeOrder(order.orderId, contract, order)
        time.sleep(1)
        app.disconnect()
        return SubmissionResult(not app.errors, str(app.next_id), "; ".join(app.errors) or "Bracket submitted to IBKR Paper")
