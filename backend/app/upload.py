from collections import Counter

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .db import get_db
from .models import Transaction
from .parsing import StatementError, parse_statement

router = APIRouter()

ALLOWED = (".csv", ".txt", ".xlsx", ".xlsm")


@router.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    spend_sign: str = Form("auto"),
    date_order: str = Form("auto"),
    db: Session = Depends(get_db),
):
    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED):
        raise HTTPException(status_code=400, detail="Please upload a .csv or .xlsx file")

    content = await file.read()
    try:
        frame, info = parse_statement(content, filename, spend_sign, date_order)
    except StatementError as e:
        raise HTTPException(status_code=400, detail=str(e))

    rows = [
        (r.date, str(r.description)[:255], round(float(r.amount), 2))
        for r in frame.itertuples()
    ]

    # Duplicate protection that still keeps genuine repeats: if the same purchase
    # appears twice on one day (two coffees), both are kept. A second upload of the
    # same file adds nothing, because the database already holds that many.
    in_db = Counter(
        (d, desc, round(float(a), 2))
        for d, desc, a in db.query(
            Transaction.date, Transaction.raw_description, Transaction.amount
        ).all()
    )
    seen = Counter()
    new_rows = []
    skipped_duplicates = 0
    for key in rows:
        seen[key] += 1
        if seen[key] <= in_db[key]:
            skipped_duplicates += 1
            continue
        new_rows.append(Transaction(date=key[0], raw_description=key[1], amount=key[2]))

    db.add_all(new_rows)
    db.commit()

    return {
        "imported": len(new_rows),
        "skipped_invalid": info["rows_skipped"],
        "skipped_duplicates": skipped_duplicates,
        "detected": info,
    }


@router.get("/transactions")
def list_transactions(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.query(Transaction).order_by(Transaction.date.desc()).limit(limit).all()
    return [
        {
            "id": t.id,
            "date": t.date,
            "description": t.raw_description,
            "amount": float(t.amount),
        }
        for t in rows
    ]
