import calendar
import json
from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import asc, desc, extract, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, CategorizationRule, Category, Transaction, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 50


def _period_income_expenses(q) -> tuple[float, float]:
    income = float(
        q.with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.amount > 0)
        .scalar()
        or 0
    )
    expenses = float(
        q.with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.amount < 0)
        .scalar()
        or 0
    )
    return income, expenses


def _user_account_ids(db: Session, user_ids: list[int]):
    """Return a subquery of account IDs belonging to the given user IDs."""
    return db.query(Account.id).filter(Account.user_id.in_(user_ids))


def _apply_user_filter(query, db: Session, user_ids: list[int]):
    if user_ids:
        query = query.filter(
            Transaction.account_id.in_(_user_account_ids(db, user_ids))
        )
    return query


def _prev_month_query(
    db: Session, month: str | None, category_id, bank, account_type, user_id
):
    """Return (query, label) for the comparison period, or (None, None)."""
    if month:
        year_int, mo_int = map(int, month.split("-"))
        prev_mo = mo_int - 1 if mo_int > 1 else 12
        prev_yr = year_int if mo_int > 1 else year_int - 1
    else:
        latest = (
            db.query(
                extract("year", Transaction.date).label("year"),
                extract("month", Transaction.date).label("month"),
            )
            .distinct()
            .order_by(
                extract("year", Transaction.date).desc(),
                extract("month", Transaction.date).desc(),
            )
            .limit(2)
            .all()
        )
        if len(latest) < 2:
            return None, None
        prev_yr, prev_mo = int(latest[1].year), int(latest[1].month)

    q = db.query(Transaction).filter(
        extract("year", Transaction.date) == prev_yr,
        extract("month", Transaction.date) == prev_mo,
    )
    if category_id:
        q = q.filter(Transaction.category_id.in_(category_id))
    if bank and bank != "unknown":
        q = q.filter(Transaction.bank == bank)
    if account_type:
        q = q.filter(
            Transaction.account_id.in_(
                db.query(Account.id).filter(Account.account_type == account_type)
            )
        )
    q = _apply_user_filter(q, db, user_id)

    import calendar as _cal

    label = f"vs {_cal.month_name[prev_mo]} {prev_yr}"
    return q, label


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


def _per_user_stats(db: Session, month: str | None) -> list[dict]:
    users = db.query(User).order_by(User.name).all()
    stats = []
    for u in users:
        account_ids = db.query(Account.id).filter(Account.user_id == u.id)
        q = db.query(Transaction).filter(Transaction.account_id.in_(account_ids))
        if month:
            year, mo = month.split("-")
            q = q.filter(
                extract("year", Transaction.date) == int(year),
                extract("month", Transaction.date) == int(mo),
            )
        income, expenses = _period_income_expenses(q)

        expense_rows = (
            db.query(
                Category.name,
                Category.color,
                func.sum(Transaction.amount).label("total"),
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .filter(
                Transaction.account_id.in_(account_ids),
                Transaction.amount < 0,
            )
        )
        if month:
            year, mo = month.split("-")
            expense_rows = expense_rows.filter(
                extract("year", Transaction.date) == int(year),
                extract("month", Transaction.date) == int(mo),
            )
        expense_rows = (
            expense_rows.group_by(Category.id)
            .order_by(func.sum(Transaction.amount))
            .all()
        )

        stats.append(
            {
                "user": u,
                "income": income,
                "expenses": expenses,
                "net": income + expenses,
                "chart_labels": json.dumps([r.name for r in expense_rows]),
                "chart_values": json.dumps(
                    [round(abs(r.total), 2) for r in expense_rows]
                ),
                "chart_colors": json.dumps([r.color for r in expense_rows]),
                "has_data": len(expense_rows) > 0,
            }
        )
    return stats


@router.get("/", response_class=HTMLResponse)
def transaction_list(
    request: Request,
    page: int = 1,
    category_id: list[int] = Query(default=[]),
    account_type: str | None = None,
    bank: str | None = None,
    month: str | None = None,
    user_id: list[int] = Query(default=[]),
    sort: str = "date",
    order: str = "desc",
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Transaction)

    if search:
        query = query.filter(Transaction.description.ilike(f"%{search}%"))
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
    query = _apply_user_filter(query, db, user_id)

    total_income, total_expenses = _period_income_expenses(query)

    prev_q, delta_label = _prev_month_query(
        db, month, category_id, bank, account_type, user_id
    )
    if prev_q is not None:
        prev_income, prev_expenses = _period_income_expenses(prev_q)
        income_delta: float | None = total_income - prev_income
        expenses_delta: float | None = total_expenses - prev_expenses
        net_delta: float | None = income_delta + expenses_delta
    else:
        income_delta = expenses_delta = net_delta = None

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
    users = db.query(User).order_by(User.name).all()
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
            "users": users,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net": total_income + total_expenses,
            "income_delta": income_delta,
            "expenses_delta": expenses_delta,
            "net_delta": net_delta,
            "delta_label": delta_label,
            "available_months": _available_months(db),
            "available_account_types": available_account_types,
            "sort": sort,
            "order": order,
            "search": search,
            "filters": {
                "category_ids": category_id,
                "bank": bank,
                "month": month,
                "account_type": account_type,
                "user_ids": user_id,
                "search": search,
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
        db.query(Transaction).filter(Transaction.description == txn.description).update(
            {"category_id": final_category_id, "is_manual_category": True},
            synchronize_session="fetch",
        )
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
    user_id: list[int] = Query(default=[]),
    db: Session = Depends(get_db),
):
    query = db.query(Transaction)
    if month:
        year, mo = month.split("-")
        query = query.filter(
            extract("year", Transaction.date) == int(year),
            extract("month", Transaction.date) == int(mo),
        )
    query = _apply_user_filter(query, db, user_id)

    expense_q = (
        db.query(
            Category.name,
            Category.color,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(Transaction.amount < 0)
    )
    if month:
        year, mo = month.split("-")
        expense_q = expense_q.filter(
            extract("year", Transaction.date) == int(year),
            extract("month", Transaction.date) == int(mo),
        )
    if user_id:
        expense_q = expense_q.filter(
            Transaction.account_id.in_(_user_account_ids(db, user_id))
        )
    expense_rows = (
        expense_q.group_by(Category.id).order_by(func.sum(Transaction.amount)).all()
    )

    chart_labels = [r.name for r in expense_rows]
    chart_values = [round(abs(r.total), 2) for r in expense_rows]
    chart_colors = [r.color for r in expense_rows]

    all_txns = query.all()
    total_income = sum(t.amount for t in all_txns if t.amount > 0)
    total_expenses = sum(t.amount for t in all_txns if t.amount < 0)
    net = total_income + total_expenses

    # Monthly histogram scoped to current user filter
    hist_q = db.query(Transaction)
    hist_q = _apply_user_filter(hist_q, db, user_id)
    all_for_hist = hist_q.all()
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

    users = db.query(User).order_by(User.name).all()
    per_user = _per_user_stats(db, month) if not user_id else []

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "month": month,
            "user_ids": user_id,
            "users": users,
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
            "per_user": per_user,
        },
    )
