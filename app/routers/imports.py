import logging
import traceback

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.importer import import_parsed_file
from app.parser import BankName, parse_qfx

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request):
    return templates.TemplateResponse(request, "import.html", {})


@router.post("/import")
async def do_import(
    request: Request,
    file: UploadFile = File(...),
    bank_hint: str = Form("auto"),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    hint: BankName | None = bank_hint if bank_hint != "auto" else None  # type: ignore[assignment]

    try:
        parsed = parse_qfx(raw, bank_hint=hint)
        result = import_parsed_file(parsed, db)
    except Exception as exc:
        logger.error(
            "Import failed for file %s:\n%s", file.filename, traceback.format_exc()
        )
        return templates.TemplateResponse(
            request,
            "import.html",
            {"error": f"Import failed: {exc}"},
        )

    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "result": result,
            "bank": parsed.bank,
            "filename": file.filename,
        },
    )
