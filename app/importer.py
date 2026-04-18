"""
Imports a ParsedFile into the database.
Primary dedup key: (fitid, bank).
Fallback dedup key: SHA-1 hash of date|amount|description (stored but not enforced
at DB level — used to surface near-duplicates in future phases).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.categorizer import categorize
from app.models import Account, Transaction
from app.parser import ParsedFile


@dataclass
class ImportResult:
    imported: int = 0
    duplicates: int = 0
    errors: int = 0


def _dedup_hash(date, amount: float, description: str) -> str:
    raw = f"{date}|{amount:.2f}|{description}".encode()
    return hashlib.sha1(raw).hexdigest()


def _get_or_create_account(db: Session, parsed: ParsedFile) -> Account:
    account = (
        db.query(Account)
        .filter_by(bank=parsed.bank, account_number=parsed.account_number)
        .first()
    )
    if not account:
        account = Account(
            bank=parsed.bank,
            account_number=parsed.account_number,
            account_type=parsed.account_type,
        )
        db.add(account)
        db.flush()
    return account


def import_parsed_file(
    parsed: ParsedFile, db: Session, user_id: int | None = None
) -> ImportResult:
    result = ImportResult()
    account = _get_or_create_account(db, parsed)
    if user_id:
        account.user_id = user_id
        db.flush()

    for ptxn in parsed.transactions:
        # Check duplicate via FITID + bank before attempting insert
        existing = (
            db.query(Transaction).filter_by(fitid=ptxn.fitid, bank=parsed.bank).first()
        )
        if existing:
            result.duplicates += 1
            continue

        category_id = categorize(ptxn.description, db)

        txn = Transaction(
            fitid=ptxn.fitid,
            bank=parsed.bank,
            account_id=account.id,
            date=ptxn.date,
            amount=ptxn.amount,
            description=ptxn.description,
            memo=ptxn.memo,
            category_id=category_id,
            is_manual_category=False,
            dedup_hash=_dedup_hash(ptxn.date, ptxn.amount, ptxn.description),
        )
        db.add(txn)

        try:
            db.flush()
            result.imported += 1
        except IntegrityError:
            db.rollback()
            result.duplicates += 1

    db.commit()
    return result
