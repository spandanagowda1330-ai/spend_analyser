import json

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import MerchantCategory, Transaction

router = APIRouter()

CATEGORIES = [
    "Groceries", "Dining", "Transport", "Entertainment", "Shopping",
    "Utilities", "Health & Fitness", "Software", "Travel", "Other",
]

FALLBACK = {
    "Netflix": "Entertainment", "Spotify": "Entertainment",
    "Disney+": "Entertainment", "Hulu": "Entertainment",
    "Anytime Fitness": "Health & Fitness", "Adobe": "Software",
    "iCloud": "Software", "Uber": "Transport", "Shell": "Transport",
    "Starbucks": "Dining", "Chipotle": "Dining", "Swiggy": "Dining",
    "Whole Foods": "Groceries", "Amazon": "Shopping",
}

SYSTEM_PROMPT = (
    "You categorize merchant names from bank statements. "
    f"Allowed categories: {', '.join(CATEGORIES)}. "
    "You will receive a JSON array of merchant names. "
    "Reply with ONLY a JSON object mapping each merchant name to exactly one "
    "allowed category. Use 'Other' if unsure."
)


def categorize_with_openai(merchants: list[str]) -> dict[str, str]:
    client = OpenAI(api_key=settings.openai_api_key)
    result: dict[str, str] = {}

    for i in range(0, len(merchants), 50):
        batch = merchants[i : i + 50]
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(batch)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        for m in batch:
            category = data.get(m)
            result[m] = category if category in CATEGORIES else "Other"
    return result


@router.post("/categorize")
def categorize(db: Session = Depends(get_db)):
    merchants = [
        m for (m,) in db.query(Transaction.merchant).distinct().all() if m
    ]
    if not merchants:
        raise HTTPException(
            status_code=400, detail="No merchants found. Call /process first."
        )

    cached = {c.merchant: c.category for c in db.query(MerchantCategory).all()}
    todo = [m for m in merchants if m not in cached]

    source = "cache"
    error = None
    if todo:
        new = None
        if settings.openai_api_key:
            try:
                new = categorize_with_openai(todo)
                source = "openai"
            except Exception as e:
                error = str(e)[:300]
        if new is None:
            new = {m: FALLBACK.get(m, "Other") for m in todo}
            source = "fallback"

        for merchant, category in new.items():
            db.add(MerchantCategory(merchant=merchant, category=category))
        cached.update(new)
        db.flush()

    for merchant in merchants:
        db.query(Transaction).filter(Transaction.merchant == merchant).update(
            {Transaction.category: cached[merchant]}
        )
    db.commit()

    return {
        "merchants_total": len(merchants),
        "from_cache": len(merchants) - len(todo),
        "newly_categorized": len(todo),
        "source": source,
        "openai_error": error,
    }


@router.get("/categories/summary")
def category_summary(db: Session = Depends(get_db)):
    rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .group_by(Transaction.category)
        .all()
    )
    total = sum(float(amount) for _, amount, _ in rows) or 1
    result = [
        {
            "category": category or "Uncategorized",
            "total": round(float(amount), 2),
            "transactions": count,
            "percent": round(float(amount) / total * 100, 1),
        }
        for category, amount, count in rows
    ]
    result.sort(key=lambda r: r["total"], reverse=True)
    return result