import logging
import traceback

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.importer import import_parsed_file
from app.models import User
from app.parser import BankName, parse_qfx

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.name).all()
    return templates.TemplateResponse(request, "import.html", {"users": users})


@router.post("/import")
async def do_import(
    request: Request,
    file: UploadFile = File(...),
    bank_hint: str = Form("auto"),
    user_id: int = Form(0),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    hint: BankName | None = bank_hint if bank_hint != "auto" else None  # type: ignore[assignment]
    users = db.query(User).order_by(User.name).all()
    uid = user_id if user_id else None

    try:
        parsed = parse_qfx(raw, bank_hint=hint)
        result = import_parsed_file(parsed, db, user_id=uid)
    except Exception as exc:
        logger.error(
            "Import failed for file %s:\n%s", file.filename, traceback.format_exc()
        )
        return templates.TemplateResponse(
            request,
            "import.html",
            {"error": f"Import failed: {exc}", "users": users},
        )

    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "result": result,
            "bank": parsed.bank,
            "filename": file.filename,
            "users": users,
        },
    )
