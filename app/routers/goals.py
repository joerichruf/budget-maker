from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BalanceEntry, Goal, Transaction

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

ACCOUNT_TYPES = ["CHECKING", "SAVINGS", "CREDITCARD", "CREDITLINE", "OTHER"]


def _avg_monthly_net(db: Session, last_n: int = 3) -> float:
    """Average net (income - expenses) over the last N months with data."""
    rows = (
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
            extract("year", Transaction.date).desc(),
            extract("month", Transaction.date).desc(),
        )
        .limit(last_n)
        .all()
    )
    if not rows:
        return 0.0
    return sum(float(r.net) for r in rows) / len(rows)


@router.get("/goals", response_class=HTMLResponse)
def goals_page(request: Request, db: Session = Depends(get_db)):
    balances = db.query(BalanceEntry).order_by(BalanceEntry.as_of_date.desc()).all()
    goals = db.query(Goal).order_by(Goal.created_at.desc()).all()
    avg_net = _avg_monthly_net(db)

    goal_details = []
    for goal in goals:
        amount_to_go = goal.starting_amount - goal.target_amount
        monthly_required = (
            amount_to_go / goal.target_months if goal.target_months else 0
        )
        gap = monthly_required - avg_net  # positive = need more savings
        months_at_current = (amount_to_go / avg_net) if avg_net > 0 else None
        goal_details.append(
            {
                "goal": goal,
                "monthly_required": round(monthly_required, 2),
                "gap": round(gap, 2),
                "months_at_current": round(months_at_current, 1)
                if months_at_current is not None
                else None,
                "on_track": gap <= 0,
            }
        )

    return templates.TemplateResponse(
        request,
        "goals.html",
        {
            "balances": balances,
            "goal_details": goal_details,
            "avg_monthly_net": round(avg_net, 2),
            "account_types": ACCOUNT_TYPES,
            "today": date.today().isoformat(),
        },
    )


@router.post("/goals/balance/add")
def add_balance(
    request: Request,
    label: str = Form(...),
    account_type: str = Form(...),
    balance: float = Form(...),
    as_of_date: str = Form(...),
    db: Session = Depends(get_db),
):
    db.add(
        BalanceEntry(
            label=label,
            account_type=account_type,
            balance=balance,
            as_of_date=date.fromisoformat(as_of_date),
        )
    )
    db.commit()
    return RedirectResponse(url="/goals", status_code=303)


@router.post("/goals/balance/{entry_id}/delete")
def delete_balance(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(BalanceEntry).filter(BalanceEntry.id == entry_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return RedirectResponse(url="/goals", status_code=303)


@router.post("/goals/add")
def add_goal(
    request: Request,
    name: str = Form(...),
    starting_amount: float = Form(...),
    target_amount: float = Form(...),
    target_months: int = Form(...),
    db: Session = Depends(get_db),
):
    db.add(
        Goal(
            name=name,
            starting_amount=starting_amount,
            target_amount=target_amount,
            target_months=target_months,
        )
    )
    db.commit()
    return RedirectResponse(url="/goals", status_code=303)


@router.post("/goals/{goal_id}/delete")
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if goal:
        db.delete(goal)
        db.commit()
    return RedirectResponse(url="/goals", status_code=303)
