import calendar
import os
import smtplib
from collections import defaultdict
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Category, CategoryBudget, Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _month_totals(db: Session, year: int, month: int) -> dict:
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(
            extract("year", Transaction.date) == year,
            extract("month", Transaction.date) == month,
        )
        .all()
    )
    income = sum(t.amount for t in txns if t.amount > 0)
    expenses = sum(t.amount for t in txns if t.amount < 0)
    by_cat: dict[int, float] = defaultdict(float)
    for t in txns:
        if t.amount < 0 and t.category_id:
            by_cat[t.category_id] += abs(t.amount)
    return {
        "income": round(income, 2),
        "expenses": round(abs(expenses), 2),
        "net": round(income + expenses, 2),
        "by_cat": dict(by_cat),
    }


def build_digest(db: Session) -> dict:
    today = date.today()
    first_of_month = date(today.year, today.month, 1)

    months_q = (
        db.query(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
        )
        .distinct()
        .filter(Transaction.date < first_of_month)
        .order_by(
            extract("year", Transaction.date).desc(),
            extract("month", Transaction.date).desc(),
        )
        .all()
    )

    if not months_q:
        return {"has_data": False}

    cur_y, cur_m = int(months_q[0].year), int(months_q[0].month)
    cur_data = _month_totals(db, cur_y, cur_m)
    cur_label = f"{calendar.month_name[cur_m]} {cur_y}"

    prev_data = None
    prev_label = None
    if len(months_q) >= 2:
        prev_y, prev_m = int(months_q[1].year), int(months_q[1].month)
        prev_data = _month_totals(db, prev_y, prev_m)
        prev_label = f"{calendar.month_name[prev_m]} {prev_y}"

    # Category-level changes vs previous month
    category_changes = []
    if prev_data:
        all_ids = set(cur_data["by_cat"]) | set(prev_data["by_cat"])
        cats = {
            c.id: c for c in db.query(Category).filter(Category.id.in_(all_ids)).all()
        }
        for cat_id in all_ids:
            if cat_id not in cats:
                continue
            cur_s = cur_data["by_cat"].get(cat_id, 0.0)
            prev_s = prev_data["by_cat"].get(cat_id, 0.0)
            category_changes.append(
                {
                    "category": cats[cat_id],
                    "cur": round(cur_s, 2),
                    "prev": round(prev_s, 2),
                    "change": round(cur_s - prev_s, 2),
                }
            )
        category_changes.sort(key=lambda x: x["change"], reverse=True)

    top_increases = [c for c in category_changes if c["change"] > 0][:3]
    top_decreases = [c for c in reversed(category_changes) if c["change"] < 0][:3]

    # Trending-up categories: 3+ consecutive months of increasing spend
    recent = months_q[:4]
    trending_up: list[dict] = []
    if len(recent) >= 3:
        cat_trend: dict[int, list[float]] = defaultdict(list)
        for m in reversed(recent):
            rows = (
                db.query(
                    Transaction.category_id,
                    func.sum(Transaction.amount).label("total"),
                )
                .filter(
                    Transaction.amount < 0,
                    extract("year", Transaction.date) == m.year,
                    extract("month", Transaction.date) == m.month,
                )
                .group_by(Transaction.category_id)
                .all()
            )
            for r in rows:
                if r.category_id:
                    cat_trend[r.category_id].append(abs(float(r.total)))

        cats_all = {c.id: c for c in db.query(Category).all()}
        for cat_id, spends in cat_trend.items():
            if len(spends) >= 3:
                last3 = spends[-3:]
                if last3[0] < last3[1] < last3[2] and cat_id in cats_all:
                    trending_up.append(
                        {
                            "category": cats_all[cat_id],
                            "spends": [round(s, 2) for s in last3],
                            "increase": round(last3[2] - last3[0], 2),
                        }
                    )
        trending_up.sort(key=lambda x: x["increase"], reverse=True)

    # Budget performance for the digest month
    budgets = db.query(CategoryBudget).join(Category).all()
    budget_perf = []
    for b in budgets:
        spent = cur_data["by_cat"].get(b.category_id, 0.0)
        budget_perf.append(
            {
                "category": b.category,
                "spent": round(spent, 2),
                "limit": b.monthly_limit,
                "over": spent > b.monthly_limit,
                "pct": min(round((spent / b.monthly_limit) * 100), 999)
                if b.monthly_limit
                else 0,
            }
        )

    smtp_configured = bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_USER")
        and os.getenv("SMTP_PASS")
        and os.getenv("DIGEST_TO")
    )

    return {
        "has_data": True,
        "cur_label": cur_label,
        "prev_label": prev_label,
        "cur": cur_data,
        "prev": prev_data,
        "net_change": round(cur_data["net"] - prev_data["net"], 2)
        if prev_data
        else None,
        "income_change": round(cur_data["income"] - prev_data["income"], 2)
        if prev_data
        else None,
        "expenses_change": round(cur_data["expenses"] - prev_data["expenses"], 2)
        if prev_data
        else None,
        "top_increases": top_increases,
        "top_decreases": top_decreases,
        "trending_up": trending_up[:5],
        "budget_perf": budget_perf,
        "over_budget_count": sum(1 for b in budget_perf if b["over"]),
        "smtp_configured": smtp_configured,
    }


def _email_html(digest: dict) -> str:
    lines = [
        "<html><body style='font-family:sans-serif;max-width:600px;margin:auto'>",
        f"<h1 style='color:#6366f1'>Monthly Digest — {digest['cur_label']}</h1>",
        "<table width='100%'><tr>",
        f"<td><strong>Net</strong><br><span style='font-size:1.4em'>${digest['cur']['net']:.2f}</span></td>",
        f"<td><strong>Income</strong><br><span style='color:#10b981'>${digest['cur']['income']:.2f}</span></td>",
        f"<td><strong>Expenses</strong><br><span style='color:#f43f5e'>${digest['cur']['expenses']:.2f}</span></td>",
        "</tr></table><hr>",
    ]
    if digest.get("top_increases"):
        lines.append("<h3>Biggest increases vs last month</h3><ul>")
        for c in digest["top_increases"]:
            lines.append(f"<li>{c['category'].name}: +${c['change']:.2f}</li>")
        lines.append("</ul>")
    if digest.get("top_decreases"):
        lines.append("<h3>Biggest savings vs last month</h3><ul>")
        for c in digest["top_decreases"]:
            lines.append(f"<li>{c['category'].name}: -${abs(c['change']):.2f}</li>")
        lines.append("</ul>")
    if digest.get("trending_up"):
        lines.append("<h3>Trending up (3 months)</h3><ul>")
        for t in digest["trending_up"]:
            lines.append(
                f"<li>{t['category'].name}: +${t['increase']:.2f} over 3 months</li>"
            )
        lines.append("</ul>")
    over = [b for b in digest.get("budget_perf", []) if b["over"]]
    if over:
        lines.append("<h3>Over budget this month</h3><ul>")
        for b in over:
            lines.append(
                f"<li>{b['category'].name}: ${b['spent']:.2f} / ${b['limit']:.2f}</li>"
            )
        lines.append("</ul>")
    lines.append("</body></html>")
    return "\n".join(lines)


def _send_email(subject: str, html: str) -> tuple[bool, str]:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    to = os.getenv("DIGEST_TO", "")

    if not all([host, user, password, to]):
        return (
            False,
            "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS, DIGEST_TO.",
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            s.starttls()
            s.login(user, password)
            s.sendmail(user, [to], msg.as_string())
        return True, f"Digest sent to {to}"
    except Exception as exc:
        return False, str(exc)


@router.get("/digest", response_class=HTMLResponse)
def digest_page(request: Request, db: Session = Depends(get_db)):
    data = build_digest(db)
    return templates.TemplateResponse(request, "digest.html", data)


@router.post("/digest/send-email")
def send_digest_email(db: Session = Depends(get_db)):
    data = build_digest(db)
    if not data.get("has_data"):
        return JSONResponse({"success": False, "message": "No digest data available."})
    html = _email_html(data)
    subject = f"Budget Digest — {data['cur_label']}"
    ok, msg = _send_email(subject, html)
    return JSONResponse({"success": ok, "message": msg})
