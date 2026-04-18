import json
import statistics
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Category, Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/insights", response_class=HTMLResponse)
def insights(request: Request, db: Session = Depends(get_db)):
    # ── Top 10 recurring transactions (most frequent descriptions) ──
    recurring = (
        db.query(
            Transaction.description,
            func.count(Transaction.id).label("count"),
            func.sum(Transaction.amount).label("total"),
            func.avg(Transaction.amount).label("avg_amount"),
        )
        .filter(Transaction.amount < 0)
        .group_by(Transaction.description)
        .having(func.count(Transaction.id) > 1)
        .order_by(func.count(Transaction.id).desc())
        .limit(10)
        .all()
    )

    # ── Top 10 expense categories ──
    top_categories_raw = (
        db.query(
            Category.id,
            Category.name,
            Category.color,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(Transaction.amount < 0)
        .group_by(Category.id)
        .order_by(func.sum(Transaction.amount))
        .limit(10)
        .all()
    )

    top_categories = []
    for cat in top_categories_raw:
        txns = (
            db.query(Transaction.date, Transaction.description, Transaction.amount)
            .filter(Transaction.category_id == cat.id, Transaction.amount < 0)
            .order_by(Transaction.amount)
            .limit(10)
            .all()
        )
        top_categories.append(
            {
                "name": cat.name,
                "color": cat.color,
                "total": cat.total,
                "count": cat.count,
                "transactions": txns,
            }
        )

    # ── Per-month net balance ──
    monthly_rows = (
        db.query(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("net"),
        )
        .group_by(
            extract("year", Transaction.date),
            extract("month", Transaction.date),
        )
        .order_by(
            extract("year", Transaction.date),
            extract("month", Transaction.date),
        )
        .all()
    )
    monthly_balance = [
        {
            "month": f"{int(r.year):04d}-{int(r.month):02d}",
            "net": round(float(r.net), 2),
        }
        for r in monthly_rows
    ]

    # ── Savings insights: per-category per-month variance ──
    all_expenses = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(Transaction.amount < 0)
        .all()
    )

    cat_monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for txn in all_expenses:
        cat = txn.category.name if txn.category else "Uncategorized"
        key = f"{txn.date.year:04d}-{txn.date.month:02d}"
        cat_monthly[cat][key] += abs(txn.amount)

    variance_data = []
    spikes = []
    for cat_name, monthly_spend in cat_monthly.items():
        values = list(monthly_spend.values())
        if len(values) >= 2:
            avg = statistics.mean(values)
            stdev = statistics.stdev(values)
            variance_data.append(
                {
                    "category": cat_name,
                    "avg_monthly": round(avg, 2),
                    "stdev": round(stdev, 2),
                }
            )
            if len(values) >= 3:
                threshold = avg + 1.5 * stdev
                for month, spend in monthly_spend.items():
                    if spend > threshold:
                        spikes.append(
                            {
                                "category": cat_name,
                                "month": month,
                                "spend": round(spend, 2),
                                "avg": round(avg, 2),
                                "excess": round(spend - avg, 2),
                            }
                        )

    variance_data.sort(key=lambda x: x["stdev"], reverse=True)
    spikes.sort(key=lambda x: x["excess"], reverse=True)

    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "recurring": recurring,
            "top_categories": top_categories,
            "monthly_balance": monthly_balance,
            "chart_months": json.dumps([r["month"] for r in monthly_balance]),
            "chart_nets": json.dumps([r["net"] for r in monthly_balance]),
            "variance_data": variance_data[:8],
            "spikes": spikes[:10],
        },
    )
