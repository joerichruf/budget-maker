import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 50


@router.get("/", response_class=HTMLResponse)
def transaction_list(
    request: Request,
    page: int = 1,
    category_id: int | None = None,
    bank: str | None = None,
    month: str | None = None,  # format: YYYY-MM
    db: Session = Depends(get_db),
):
    query = db.query(Transaction)

    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if bank and bank != "unknown":
        query = query.filter(Transaction.bank == bank)
    if month:
        year, mo = month.split("-")
        query = query.filter(
            extract("year", Transaction.date) == int(year),
            extract("month", Transaction.date) == int(mo),
        )

    total = query.count()
    transactions = (
        query.order_by(Transaction.date.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )

    categories = db.query(Category).order_by(Category.name).all()
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
            "filters": {
                "category_id": category_id,
                "bank": bank,
                "month": month,
            },
        },
    )


@router.post("/transactions/{txn_id}/category")
def update_category(
    txn_id: int,
    category_id: int = Form(...),
    db: Session = Depends(get_db),
):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if txn:
        txn.category_id = category_id
        txn.is_manual_category = True
        db.commit()
    return RedirectResponse(url="/", status_code=303)


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

    # Expenses pie chart — negative amounts only, grouped by category
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

    # Summary totals
    all_txns = query.all()
    total_income = sum(t.amount for t in all_txns if t.amount > 0)
    total_expenses = sum(t.amount for t in all_txns if t.amount < 0)
    net = total_income + total_expenses

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
        },
    )
