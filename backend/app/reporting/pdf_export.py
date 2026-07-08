"""End-of-session explainable trade log PDF - the mandatory "Complete
Explainable Trade Log PDF" deliverable, generated once a session closes."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.db.models import Decision, Portfolio, Trade

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def generate_session_report(db: Session, portfolio: Portfolio) -> str:
    trades = db.query(Trade).filter_by(portfolio_id=portfolio.id).order_by(Trade.timestamp).all()
    decisions = db.query(Decision).order_by(Decision.timestamp).all()

    net_profit = portfolio.cash_inr - portfolio.starting_capital
    total_return_pct = (net_profit / portfolio.starting_capital) * 100 if portfolio.starting_capital else 0.0

    closing_trades = [t for t in trades if t.position and t.position.status == "closed"]
    wins = sum(1 for t in trades if t.position_id and t.position and t.position.realized_pnl and t.position.realized_pnl > 0)
    win_rate = (wins / len(closing_trades) * 100) if closing_trades else 0.0

    filename = f"session_report_{portfolio.id}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = REPORTS_DIR / filename

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Autonomous Multi-Agent Investment Committee", styles["Title"]),
        Paragraph("Explainable Trade Log — Session Report", styles["Heading2"]),
        Spacer(1, 12),
        Paragraph(
            f"Starting Capital: ₹{portfolio.starting_capital:,.2f} | Final Portfolio Value: ₹{portfolio.cash_inr:,.2f} | "
            f"Net Profit: ₹{net_profit:,.2f} | Total Return: {total_return_pct:+.2f}% | Win Rate: {win_rate:.1f}%",
            styles["Normal"],
        ),
        Spacer(1, 16),
        Paragraph("Trade History", styles["Heading3"]),
    ]

    trade_rows = [["Time", "Symbol", "Action", "Qty", "Price", "Costs", "Net Cash Impact"]]
    for t in trades:
        trade_rows.append(
            [t.timestamp.strftime("%H:%M:%S"), t.symbol, t.action, str(t.quantity), f"₹{t.price:,.2f}", f"₹{t.total_costs:,.2f}", f"₹{t.net_cash_impact:,.2f}"]
        )
    trade_table = Table(trade_rows, repeatRows=1)
    trade_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E2761")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(trade_table)
    story.append(Spacer(1, 16))
    story.append(Paragraph("Explainable Decision Log (every trade & no-trade)", styles["Heading3"]))

    for d in decisions:
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>{d.symbol}</b> — {d.verdict} ({d.directional_confidence:.1f}% directional confidence) — {d.timestamp.strftime('%H:%M:%S')}", styles["Heading4"]))
        story.append(Paragraph(d.consensus_reasoning, styles["Normal"]))

    doc.build(story)
    return str(path)
