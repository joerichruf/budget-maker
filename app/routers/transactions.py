from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
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
    if bank:
        query = query.filter(Transaction.bank == bank)
    if month:
        year, mo = month.split("-")
        from sqlalchemy import extract

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
        "transactions.html",
        {
            "request": request,
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
