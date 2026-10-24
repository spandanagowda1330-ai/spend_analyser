import json

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .merchants import guess_category
from .models import MerchantCategory, Transaction

router = APIRouter()

CATEGORIES = [
    "Groceries", "Dining", "Transport", "Entertainment", "Shopping",
    "Utilities", "Health & Fitness", "Software", "Education", "Housing", "Cash", "Travel", "Other",
]

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
    # one example of the original bank text per merchant, used as a hint
    samples = dict(
        db.query(Transaction.merchant, func.min(Transaction.raw_description))
        .filter(Transaction.merchant.isnot(None))
        .group_by(Transaction.merchant)
        .all()
    )
    merchants = list(samples)
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
                # Only paid AI answers are cached. Rule-based guesses are recomputed
                # each time, so improving the rules improves old data too.
                for merchant, category in new.items():
                    db.add(MerchantCategory(merchant=merchant, category=category))
            except Exception as e:  # network, bad key, no credit, ...
                error = str(e)[:300]
                new = None
        if new is None:
            new = {m: guess_category(m, samples[m]) for m in todo}
            source = "fallback"
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
