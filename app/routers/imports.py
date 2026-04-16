from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.importer import import_parsed_file
from app.parser import BankName, parse_qfx

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
    except Exception as exc:
        return templates.TemplateResponse(
            request, "import.html", {"error": f"Failed to parse file: {exc}"}
        )

    result = import_parsed_file(parsed, db)

    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "result": result,
            "bank": parsed.bank,
            "filename": file.filename,
        },
    )
