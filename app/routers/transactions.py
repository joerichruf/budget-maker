import calendar
import json
from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import asc, desc, extract, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, CategorizationRule, Category, Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 50


def _available_months(db: Session) -> list[dict]:
    rows = (
        db.query(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
        )
        .distinct()
        .order_by(
            extract("year", Transaction.date).desc(),
            extract("month", Transaction.date).desc(),
        )
        .all()
    )
    return [
        {
            "value": f"{int(r.year):04d}-{int(r.month):02d}",
            "display": f"{calendar.month_name[int(r.month)]} {int(r.year)}",
        }
        for r in rows
    ]


@router.get("/", response_class=HTMLResponse)
def transaction_list(
    request: Request,
    page: int = 1,
    category_id: list[int] = Query(default=[]),
    account_type: str | None = None,
    bank: str | None = None,
    month: str | None = None,
    sort: str = "date",
    order: str = "desc",
    db: Session = Depends(get_db),
):
    query = db.query(Transaction)

    if category_id:
        query = query.filter(Transaction.category_id.in_(category_id))
    if bank and bank != "unknown":
        query = query.filter(Transaction.bank == bank)
    if month:
        year, mo = month.split("-")
        query = query.filter(
            extract("year", Transaction.date) == int(year),
            extract("month", Transaction.date) == int(mo),
        )
    if account_type:
        query = query.filter(
            Transaction.account_id.in_(
                db.query(Account.id).filter(Account.account_type == account_type)
            )
        )

    total_income = float(
        query.with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.amount > 0)
        .scalar()
        or 0
    )
    total_expenses = float(
        query.with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.amount < 0)
        .scalar()
        or 0
    )

    total = query.count()

    order_fn = desc if order == "desc" else asc
    if sort == "amount":
        sort_col = Transaction.amount
    elif sort == "account_type":
        query = query.join(Account, Transaction.account_id == Account.id, isouter=True)
        sort_col = Account.account_type
    else:
        sort_col = Transaction.date

    transactions = (
        query.order_by(order_fn(sort_col))
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )

    categories = db.query(Category).order_by(Category.name).all()
    available_account_types = [
        r[0]
        for r in db.query(Account.account_type)
        .distinct()
        .order_by(Account.account_type)
        .all()
        if r[0]
    ]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse(
        request,
        "transactions.html",
        {
            "transactions": transactions,
            "categories": categories,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net": total_income + total_expenses,
            "available_months": _available_months(db),
            "available_account_types": available_account_types,
            "sort": sort,
            "order": order,
            "filters": {
                "category_ids": category_id,
                "bank": bank,
                "month": month,
                "account_type": account_type,
            },
        },
    )


@router.post("/transactions/{txn_id}/category")
def update_category(
    request: Request,
    txn_id: int,
    category_id: int = Form(...),
    new_category_name: str | None = Form(None),
    new_category_color: str = Form("#9E9E9E"),
    apply_to_all: str | None = Form(None),
    db: Session = Depends(get_db),
):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        return RedirectResponse(
            url=request.headers.get("referer", "/"), status_code=303
        )

    # Create a new category if a name was provided
    name = (new_category_name or "").strip()
    if name:
        existing = db.query(Category).filter(Category.name == name).first()
        if existing:
            final_category_id = existing.id
        else:
            cat = Category(name=name, color=new_category_color, is_income=False)
            db.add(cat)
            db.flush()
            final_category_id = cat.id
    else:
        final_category_id = category_id

    if apply_to_all:
        # Bulk-update all transactions sharing the same description
        db.query(Transaction).filter(Transaction.description == txn.description).update(
            {"category_id": final_category_id, "is_manual_category": True},
            synchronize_session="fetch",
        )
        # Upsert a categorization rule so future imports get tagged automatically
        existing_rule = (
            db.query(CategorizationRule)
            .filter(CategorizationRule.pattern == txn.description)
            .first()
        )
        if existing_rule:
            existing_rule.category_id = final_category_id
            existing_rule.priority = 10
        else:
            db.add(
                CategorizationRule(
                    pattern=txn.description,
                    category_id=final_category_id,
                    priority=10,
                )
            )
    else:
        txn.category_id = final_category_id
        txn.is_manual_category = True

    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/"), status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    month: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Transaction)
    if month:
        year, mo = month.split("-")
        query = query.filter(
            extract("year", Transaction.date) == int(year),
            extract("month", Transaction.date) == int(mo),
        )

    expense_rows = (
        db.query(
            Category.name,
            Category.color,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(Transaction.amount < 0)
        .group_by(Category.id)
    )
    if month:
        year, mo = month.split("-")
        expense_rows = expense_rows.filter(
            extract("year", Transaction.date) == int(year),
            extract("month", Transaction.date) == int(mo),
        )
    expense_rows = expense_rows.order_by(func.sum(Transaction.amount)).all()

    chart_labels = [r.name for r in expense_rows]
    chart_values = [round(abs(r.total), 2) for r in expense_rows]
    chart_colors = [r.color for r in expense_rows]

    all_txns = query.all()
    total_income = sum(t.amount for t in all_txns if t.amount > 0)
    total_expenses = sum(t.amount for t in all_txns if t.amount < 0)
    net = total_income + total_expenses

    # Monthly histogram — always unfiltered for full picture
    all_for_hist = db.query(Transaction).all()
    m_income: dict[str, float] = defaultdict(float)
    m_expenses: dict[str, float] = defaultdict(float)
    for t in all_for_hist:
        key = f"{t.date.year:04d}-{t.date.month:02d}"
        if t.amount > 0:
            m_income[key] += t.amount
        else:
            m_expenses[key] += abs(t.amount)
    all_hist_months = sorted(set(list(m_income) + list(m_expenses)))
    histogram_labels = all_hist_months
    histogram_income = [round(m_income[m], 2) for m in all_hist_months]
    histogram_expenses = [round(m_expenses[m], 2) for m in all_hist_months]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "month": month,
            "chart_labels": json.dumps(chart_labels),
            "chart_values": json.dumps(chart_values),
            "chart_colors": json.dumps(chart_colors),
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net": net,
            "has_data": len(expense_rows) > 0,
            "available_months": _available_months(db),
            "histogram_labels": json.dumps(histogram_labels),
            "histogram_income": json.dumps(histogram_income),
            "histogram_expenses": json.dumps(histogram_expenses),
        },
    )
