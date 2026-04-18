import statistics
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _day_spread(days: list[int]) -> int:
    """Minimum circular span of day-of-month values in a 31-day cycle."""
    lo, hi = min(days), max(days)
    return min(hi - lo, 31 - hi + lo)


def _ordinal(n: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(
        n % 10 if n % 100 not in (11, 12, 13) else 0, "th"
    )
    return f"{n}{suffix}"


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
        grouped[t.description].append(t)

    today = date.today()
    subscriptions = []

    for key, group in grouped.items():
        if len(group) < 3:
            continue

        dates = sorted(t.date for t in group)
        dom = [d.day for d in dates]
        if _day_spread(dom) > 3:
            continue

        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

        last_txn = max(group, key=lambda t: t.date)
        amount = abs(last_txn.amount)
        if all(25 <= g <= 45 for g in gaps):
            cadence = "monthly"
            monthly_cost = amount
        elif all(330 <= g <= 400 for g in gaps):
            cadence = "annual"
            monthly_cost = amount / 12
        else:
            continue

        billing_day = round(statistics.mean(dom))
        last_date = dates[-1]
        days_since = (today - last_date).days

        # Estimate next charge date
        if cadence == "monthly":
            year, month = today.year, today.month
            if today.day > billing_day:
                month += 1
                if month > 12:
                    month, year = 1, year + 1
            try:
                next_charge = date(year, month, billing_day)
            except ValueError:
                # billing_day doesn't exist in that month (e.g. 31st in April)
                next_charge = date(year, month, 1) + timedelta(days=billing_day - 1)
        else:
            next_charge = last_date.replace(year=last_date.year + 1)

        subscriptions.append(
            {
                "display_name": last_txn.description,
                "cadence": cadence,
                "count": len(group),
                "last_charge": last_date,
                "days_since": days_since,
                "amount": round(amount, 2),
                "monthly_cost": round(monthly_cost, 2),
                "annual_cost": round(monthly_cost * 12, 2),
                "forgotten": days_since > 60,
                "category": last_txn.category,
                "billing_day": billing_day,
                "billing_day_label": _ordinal(billing_day),
                "next_charge": next_charge,
            }
        )

    subscriptions.sort(key=lambda x: x["monthly_cost"], reverse=True)
    return subscriptions


@router.get("/subscriptions", response_class=HTMLResponse)
def subscriptions_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    subs = detect_subscriptions(db)
    if q:
        q_lower = q.lower()
        subs = [s for s in subs if q_lower in s["display_name"].lower()]
    total_monthly = round(sum(s["monthly_cost"] for s in subs), 2)
    return templates.TemplateResponse(
        request,
        "subscriptions.html",
        {
            "subscriptions": subs,
            "total_monthly": total_monthly,
            "total_annual": round(total_monthly * 12, 2),
            "forgotten_count": sum(1 for s in subs if s["forgotten"]),
            "q": q,
        },
    )
