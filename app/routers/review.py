from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CategorizationRule, Category, Transaction
from app.services.categorizer_ai import suggest_categories

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _other_category_id(db: Session) -> int | None:
    cat = db.query(Category).filter(Category.name == "Other").first()
    return cat.id if cat else None


@router.get("/review", response_class=HTMLResponse)
def review_page(request: Request, db: Session = Depends(get_db)):
    other_id = _other_category_id(db)
    if other_id is None:
        rows = []
    else:
        rows = (
            db.query(
                Transaction.description,
                func.count(Transaction.id).label("count"),
                func.sum(Transaction.amount).label("total"),
            )
            .filter(
                Transaction.category_id == other_id,
                Transaction.amount < 0,
            )
            .group_by(Transaction.description)
            .order_by(func.sum(Transaction.amount))
            .all()
        )

    categories = db.query(Category).order_by(Category.name).all()
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "rows": rows,
            "categories": categories,
        },
    )


@router.get("/review/suggestions")
def get_suggestions(db: Session = Depends(get_db)):
    """Return AI-suggested categories for all uncategorized 'Other' expenses."""
    other_id = _other_category_id(db)
    if other_id is None:
        return JSONResponse({})

    # Build {description: current_category_name} for filtering
    rows = (
        db.query(Transaction.description, Category.name)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Transaction.category_id == other_id, Transaction.amount < 0)
        .distinct()
        .all()
    )

    if not rows:
        return JSONResponse({})

    current_category = {desc: cat_name for desc, cat_name in rows}
    suggestions = suggest_categories(list(current_category.keys()))

    # Never suggest the category a transaction is already assigned to
    filtered = {
        desc: cat
        for desc, cat in suggestions.items()
        if cat != current_category.get(desc)
    }
    return JSONResponse(filtered)


@router.post("/review/apply")
def apply_single(
    request: Request,
    description: str = Form(...),
    category_id: int = Form(...),
    db: Session = Depends(get_db),
):
    """Apply a category to all transactions matching the given description."""
    db.query(Transaction).filter(Transaction.description == description).update(
        {"category_id": category_id, "is_manual_category": True},
        synchronize_session="fetch",
    )
    existing = (
        db.query(CategorizationRule)
        .filter(CategorizationRule.pattern == description)
        .first()
    )
    if existing:
        existing.category_id = category_id
    else:
        db.add(
            CategorizationRule(
                pattern=description, category_id=category_id, priority=10
            )
        )
    db.commit()
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse({"ok": True})
    return RedirectResponse(url="/review", status_code=303)


@router.post("/review/apply-batch")
async def apply_batch(request: Request, db: Session = Depends(get_db)):
    """Accept a JSON body {description: category_name} and apply all at once."""
    body = await request.json()
    cats = {c.name: c for c in db.query(Category).all()}
    applied = 0
    for description, category_name in body.items():
        cat = cats.get(category_name)
        if not cat:
            continue
        db.query(Transaction).filter(Transaction.description == description).update(
            {"category_id": cat.id, "is_manual_category": True},
            synchronize_session="fetch",
        )
        existing = (
            db.query(CategorizationRule)
            .filter(CategorizationRule.pattern == description)
            .first()
        )
        if existing:
            existing.category_id = cat.id
        else:
            db.add(
                CategorizationRule(pattern=description, category_id=cat.id, priority=10)
            )
        applied += 1
    db.commit()
    return JSONResponse({"applied": applied})
