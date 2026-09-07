from __future__ import annotations

import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .models import ProposalStatus
from .store import ProposalStore


def serve_dashboard(store: ProposalStore, host: str = "127.0.0.1", port: int = 8765) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: str, status=HTTPStatus.OK):
            payload = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            if urlparse(self.path).path != "/":
                return self._send("Not found", HTTPStatus.NOT_FOUND)
            rows = []
            for proposal in store.list():
                actions = ""
                if proposal.status == ProposalStatus.PENDING_APPROVAL:
                    token = html.escape(proposal.approval_token)
                    actions = f"<form method='post' action='/decision'><input type='hidden' name='token' value='{token}'><button name='decision' value='approve'>Approve</button><button name='decision' value='reject'>Reject</button></form>"
                rows.append(f"<tr><td>{html.escape(proposal.symbol)}</td><td>{proposal.score}</td><td>{proposal.trigger_price}</td><td>{proposal.stop_loss_price}</td><td>{proposal.quantity}</td><td>{proposal.status.value}</td><td>{actions}</td></tr>")
            self._send("<!doctype html><meta charset='utf-8'><title>TrendPilot proposals</title><h1>TrendPilot proposals</h1><p>Approval changes state only; it does not submit an order.</p><table><tr><th>Symbol</th><th>Score</th><th>Trigger</th><th>Stop</th><th>Qty</th><th>Status</th><th>Decision</th></tr>" + "".join(rows) + "</table>")

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/decision":
                return self._send("Not found", HTTPStatus.NOT_FOUND)
            form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
            try:
                store.decide(form.get("token", [""])[0], form.get("decision", [""])[0] == "approve")
            except ValueError as exc:
                return self._send(html.escape(str(exc)), HTTPStatus.BAD_REQUEST)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, format, *args):
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()

