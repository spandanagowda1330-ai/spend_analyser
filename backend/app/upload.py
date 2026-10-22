import io

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .db import get_db
from .models import Transaction

router = APIRouter()

REQUIRED_COLUMNS = {"date", "description", "amount"}


@router.post("/upload")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read the CSV file")

    df.columns = [c.strip().lower() for c in df.columns]
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Missing columns: {sorted(missing)}"
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    valid = df.dropna(subset=["date", "description", "amount"])
    skipped_invalid = len(df) - len(valid)

    existing = {
        (d, desc, float(amt))
        for d, desc, amt in db.query(
            Transaction.date, Transaction.raw_description, Transaction.amount
        ).all()
    }

    new_rows = []
    skipped_duplicates = 0
    for row in valid.itertuples():
        key = (row.date.date(), str(row.description).strip(), float(row.amount))
        if key in existing:
            skipped_duplicates += 1
            continue
        existing.add(key)
        new_rows.append(
            Transaction(
                date=key[0],
                raw_description=key[1][:255],
                amount=key[2],
            )
        )

    db.add_all(new_rows)
    db.commit()

    return {
        "imported": len(new_rows),
        "skipped_invalid": skipped_invalid,
        "skipped_duplicates": skipped_duplicates,
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