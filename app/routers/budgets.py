import calendar
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, CategoryBudget, Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _current_month_spending(db: Session) -> dict[int, float]:
    today = date.today()
    rows = (
        db.query(Transaction.category_id, func.sum(Transaction.amount).label("total"))
        .filter(
            Transaction.amount < 0,
            extract("year", Transaction.date) == today.year,
            extract("month", Transaction.date) == today.month,
        )
        .group_by(Transaction.category_id)
        .all()
    )
    return {r.category_id: abs(float(r.total)) for r in rows if r.category_id}


def _trend(spent: float, day_of_month: int, days_in_month: int) -> float:
    if day_of_month <= 0:
        return 0.0
    return round((spent / day_of_month) * days_in_month, 2)


@router.get("/budgets", response_class=HTMLResponse)
def budgets_page(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    spending = _current_month_spending(db)

    budgets = (
        db.query(CategoryBudget)
        .join(Category)
        .filter(Category.is_income.is_(False))
        .order_by(Category.name)
        .all()
    )

    budget_rows = []
    for b in budgets:
        spent = spending.get(b.category_id, 0.0)
        remaining = b.monthly_limit - spent
        projected = _trend(spent, today.day, days_in_month)
        budget_rows.append(
            {
                "budget": b,
                "spent": round(spent, 2),
                "remaining": round(remaining, 2),
                "over": remaining < 0,
                "pct": min(round((spent / b.monthly_limit) * 100), 100)
                if b.monthly_limit
                else 0,
                "projected": projected,
                "trend_over": projected > b.monthly_limit,
            }
        )

    categories = (
        db.query(Category)
        .filter(Category.is_income.is_(False))
        .order_by(Category.name)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "budgets.html",
        {
            "budget_rows": budget_rows,
            "categories": categories,
            "today": today,
            "days_in_month": days_in_month,
        },
    )


@router.post("/budgets/set")
def set_budget(
    request: Request,
    category_id: int = Form(...),
    monthly_limit: float = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(CategoryBudget).filter_by(category_id=category_id).first()
    if existing:
        existing.monthly_limit = monthly_limit
    else:
        db.add(CategoryBudget(category_id=category_id, monthly_limit=monthly_limit))
    db.commit()
    return RedirectResponse(
        url=request.headers.get("referer", "/budgets"), status_code=303
    )


@router.post("/budgets/{budget_id}/delete")
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    b = db.query(CategoryBudget).filter_by(id=budget_id).first()
    if b:
        db.delete(b)
        db.commit()
    return RedirectResponse(url="/budgets", status_code=303)
