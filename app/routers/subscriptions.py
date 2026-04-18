import re
import statistics
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_TRAILING_STORE = re.compile(r"\s*#\d+\s*$")


def _normalize(desc: str) -> str:
    return _TRAILING_STORE.sub("", desc).strip()


def detect_subscriptions(db: Session) -> list[dict]:
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(Transaction.amount < 0)
        .order_by(Transaction.date)
        .all()
    )

    grouped: dict[str, list] = defaultdict(list)
    for t in txns:
        key = _normalize(t.description).upper()
        grouped[key].append(t)

    today = date.today()
    subscriptions = []

    for key, group in grouped.items():
        if len(group) < 2:
            continue

        dates = sorted(t.date for t in group)
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        avg_gap = statistics.mean(gaps)

        amounts = [abs(t.amount) for t in group]
        mean_amt = statistics.mean(amounts)
        if mean_amt > 0 and len(amounts) >= 2:
            cv = statistics.stdev(amounts) / mean_amt
            if cv > 0.3:
                continue

        if 25 <= avg_gap <= 40:
            cadence = "monthly"
            monthly_cost = mean_amt
        elif 330 <= avg_gap <= 400:
            cadence = "annual"
            monthly_cost = mean_amt / 12
        else:
            continue

        last_txn = max(group, key=lambda t: t.date)
        days_since = (today - last_txn.date).days

        subscriptions.append(
            {
                "display_name": _normalize(last_txn.description) or key,
                "cadence": cadence,
                "count": len(group),
                "last_charge": last_txn.date,
                "days_since": days_since,
                "avg_amount": round(mean_amt, 2),
                "monthly_cost": round(monthly_cost, 2),
                "annual_cost": round(monthly_cost * 12, 2),
                "forgotten": days_since > 60,
                "category": last_txn.category,
            }
        )

    subscriptions.sort(key=lambda x: x["monthly_cost"], reverse=True)
    return subscriptions


@router.get("/subscriptions", response_class=HTMLResponse)
def subscriptions_page(request: Request, db: Session = Depends(get_db)):
    subs = detect_subscriptions(db)
    total_monthly = round(sum(s["monthly_cost"] for s in subs), 2)
    return templates.TemplateResponse(
        request,
        "subscriptions.html",
        {
            "subscriptions": subs,
            "total_monthly": total_monthly,
            "total_annual": round(total_monthly * 12, 2),
            "forgotten_count": sum(1 for s in subs if s["forgotten"]),
        },
    )
