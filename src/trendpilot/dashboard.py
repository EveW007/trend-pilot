from __future__ import annotations

import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .models import ProposalStatus
from .store import ProposalStore


def _money(value: float) -> str:
    return f"${value:,.2f}"


def serve_dashboard(store: ProposalStore, host: str = "127.0.0.1", port: int = 8765) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path != "/":
                self._send("Not found", HTTPStatus.NOT_FOUND)
                return
            rows = []
            for proposal in store.list():
                actions = ""
                if proposal.status == ProposalStatus.PENDING_APPROVAL:
                    actions = f"""
                    <form method='post' action='/decision'>
                      <input type='hidden' name='token' value='{html.escape(proposal.approval_token)}'>
                      <button name='decision' value='approve' class='approve'>批准</button>
                      <button name='decision' value='reject' class='reject'>拒绝</button>
                    </form>"""
                rows.append(
                    f"""<tr><td>{html.escape(proposal.symbol)}</td><td>{proposal.score:.1f}</td>
                    <td>{_money(proposal.trigger_price)} / {_money(proposal.limit_price)}</td>
                    <td>{_money(proposal.stop_loss_price)}</td><td>{proposal.quantity}</td>
                    <td>{_money(proposal.estimated_risk)}</td><td>{proposal.status.value}</td><td>{actions}</td></tr>"""
                )
            body = f"""<!doctype html><html lang='zh'><meta charset='utf-8'>
            <title>TrendPilot 提案</title><style>
            body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:40px;background:#f6f7f9;color:#17202a}}
            table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}
            button{{padding:8px 14px;border:0;border-radius:7px;color:white;margin-right:8px;cursor:pointer}}
            .approve{{background:#157347}}.reject{{background:#b02a37}}.note{{background:#fff3cd;padding:14px;border-radius:8px}}
            </style><h1>TrendPilot 订单提案</h1>
            <p class='note'>批准只改变提案状态，不会自动提交订单。提交IBKR Paper仍需要在终端执行第二道明确确认。</p>
            <table><thead><tr><th>股票</th><th>评分</th><th>触发/最高买价</th><th>止损</th><th>股数</th><th>预计风险</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>{''.join(rows)}</tbody></table></html>"""
            self._send(body)

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/decision":
                self._send("Not found", HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            token = form.get("token", [""])[0]
            decision = form.get("decision", [""])[0]
            try:
                store.decide(token, approve=decision == "approve")
            except ValueError as exc:
                self._send(html.escape(str(exc)), HTTPStatus.BAD_REQUEST)
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"TrendPilot dashboard: http://{host}:{port}")
    server.serve_forever()

