from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.name).all()
    accounts = db.query(Account).order_by(Account.bank, Account.account_number).all()
    return templates.TemplateResponse(
        request, "users.html", {"users": users, "accounts": accounts}
    )


@router.post("/users")
def create_user(
    request: Request,
    name: str = Form(...),
    color: str = Form("#6366f1"),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if name and not db.query(User).filter_by(name=name).first():
        db.add(User(name=name, color=color))
        db.commit()
    return RedirectResponse(url="/users", status_code=303)


@router.post("/users/{user_id}/delete")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.query(Account).filter(Account.user_id == user_id).update(
            {"user_id": None}, synchronize_session="fetch"
        )
        db.delete(user)
        db.commit()
    return RedirectResponse(url="/users", status_code=303)


@router.post("/accounts/{account_id}/assign")
def assign_account(
    request: Request,
    account_id: int,
    user_id: int = Form(...),
    db: Session = Depends(get_db),
):
    account = db.query(Account).filter(Account.id == account_id).first()
    if account:
        account.user_id = user_id if user_id else None
        db.commit()
    return RedirectResponse(url="/users", status_code=303)
