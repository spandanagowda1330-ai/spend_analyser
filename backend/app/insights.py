import json
import re

from fastapi import APIRouter, Depends
from openai import OpenAI
from sqlalchemy import func
from sqlalchemy.orm import Session

from .analytics import spikes
from .config import settings
from .db import get_db
from .models import Insight, Subscription, Transaction
from .subscriptions import CHARGES_PER_YEAR

router = APIRouter()

VIDEO_STREAMING = {
    "Netflix", "Disney+", "Hulu", "Prime Video", "Hbo Max", "Peacock",
    "Paramount+", "Apple Tv", "Hotstar",
}

POLISH_PROMPT = (
    "You are a friendly personal-finance assistant. You will receive a JSON "
    "array of short insights about a user's spending. Rewrite each one in a "
    "warm, clear tone, at most 2 sentences, and include one concrete next "
    "step. Keep every dollar amount, percentage, date and merchant name "
    "exactly as given. Never add new numbers or facts. Reply with ONLY a "
    'JSON object like {"messages": [...]} containing the same number of '
    "items in the same order."
)


def money(x: float) -> str:
    return f"${x:,.2f}"


def annual_cost(s: Subscription) -> float:
    return float(s.amount) * CHARGES_PER_YEAR[s.frequency]


def build_insights(db: Session) -> list[dict]:
    insights: list[dict] = []
    subs = db.query(Subscription).all()
    active = [s for s in subs if s.status == "active"]

    # 1. Overlapping video streaming services
    streaming = sorted(
        (s for s in active if s.merchant in VIDEO_STREAMING),
        key=lambda s: float(s.amount),
        reverse=True,
    )
    if len(streaming) >= 2:
        monthly = sum(annual_cost(s) for s in streaming) / 12
        savings = sum(annual_cost(s) for s in streaming[1:])  # keep the priciest
        names = ", ".join(s.merchant for s in streaming)
        insights.append(
            {
                "type": "overlap",
                "message": (
                    f"You pay for {len(streaming)} video streaming services "
                    f"({names}) costing {money(monthly)} a month. Keeping one "
                    f"and rotating the others when a show you want comes out "
                    f"could save at least {money(savings)} a year."
                ),
                "savings": round(savings, 2),
            }
        )

    # 2. Price hikes and fitness memberships
    for s in active:
        txns = sorted(s.transactions, key=lambda t: t.date)
        if not txns:
            continue

        first, latest = float(txns[0].amount), float(s.amount)
        if first > 0 and latest - first > 0.005:
            pct = (latest - first) / first * 100
            extra = (latest - first) * CHARGES_PER_YEAR[s.frequency]
            insights.append(
                {
                    "type": "price_hike",
                    "message": (
                        f"{s.merchant} raised its price from {money(first)} to "
                        f"{money(latest)} (up {pct:.0f}%). That costs you an "
                        f"extra {money(extra)} a year. Check whether a cheaper "
                        f"plan exists or whether it is still worth it."
                    ),
                    "savings": None,
                }
            )

        if txns[0].category == "Health & Fitness":
            paid = sum(float(t.amount) for t in txns)
            insights.append(
                {
                    "type": "forgotten",
                    "message": (
                        f"{s.merchant} is a fitness membership, and these are "
                        f"easy to forget about. You have paid {money(paid)} "
                        f"over {len(txns)} months. If you are not going "
                        f"regularly, cancelling would save {money(annual_cost(s))} "
                        f"a year."
                    ),
                    "savings": round(annual_cost(s), 2),
                }
            )

    # 3. Most expensive subscription
    if len(active) >= 2:
        biggest = max(active, key=annual_cost)
        total = sum(annual_cost(s) for s in active)
        insights.append(
            {
                "type": "review",
                "message": (
                    f"{biggest.merchant} is your most expensive subscription at "
                    f"{money(annual_cost(biggest))} a year "
                    f"({annual_cost(biggest) / total * 100:.0f}% of your "
                    f"subscription spending). Make sure you use it enough to "
                    f"justify the cost."
                ),
                "savings": None,
            }
        )

    # 4. Subscriptions that seem to have stopped
    for s in subs:
        if s.status == "possibly_cancelled":
            insights.append(
                {
                    "type": "check",
                    "message": (
                        f"{s.merchant} has not charged since {s.last_charged}. "
                        f"It looks cancelled, but confirm you are not still "
                        f"subscribed."
                    ),
                    "savings": None,
                }
            )

    # 5. Spending spikes
    for sp in spikes(db)[:2]:
        insights.append(
            {
                "type": "spike",
                "message": (
                    f"{sp['category']} spending hit {money(sp['amount'])} in "
                    f"{sp['month']}, compared with about {money(sp['usual'])} "
                    f"in a typical month. Worth checking what drove the jump."
                ),
                "savings": None,
            }
        )

    # 6. Biggest category
    rows = (
        db.query(Transaction.category, func.sum(Transaction.amount))
        .filter(Transaction.category.isnot(None))
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    grand_total = sum(float(a) for _, a in rows)
    if rows and grand_total:
        category, amount = rows[0]
        insights.append(
            {
                "type": "info",
                "message": (
                    f"{category} is your biggest spending category at "
                    f"{money(float(amount))} "
                    f"({float(amount) / grand_total * 100:.0f}% of everything "
                    f"you spent)."
                ),
                "savings": None,
            }
        )

    # Biggest savings first (sort is stable, so the rest keep their order)
    insights.sort(key=lambda i: i["savings"] or 0, reverse=True)
    return insights


def polish_with_openai(messages: list[str]) -> list[str]:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": POLISH_PROMPT},
            {"role": "user", "content": json.dumps(messages)},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    data = json.loads(response.choices[0].message.content)
    polished = data.get("messages", [])
    if len(polished) != len(messages):
        raise ValueError("Model returned the wrong number of messages")

    result = []
    for original, new in zip(messages, polished):
        # Every dollar amount and percentage must survive the rewrite
        facts = re.findall(r"\$[\d,]+(?:\.\d+)?|\d+%", original)
        ok = isinstance(new, str) and all(f in new for f in facts)
        result.append(new if ok else original)
    return result


@router.post("/insights/generate")
def generate(db: Session = Depends(get_db)):
    items = build_insights(db)
    source = "rules"
    error = None

    if items and settings.openai_api_key:
        try:
            polished = polish_with_openai([i["message"] for i in items])
            for item, text in zip(items, polished):
                item["message"] = text
            source = "openai"
        except Exception as e:
            error = str(e)[:300]

    db.query(Insight).delete()
    for i in items:
        db.add(
            Insight(
                type=i["type"],
                message=i["message"][:500],
                estimated_savings=i["savings"],
            )
        )
    db.commit()
    return {"insights": len(items), "source": source, "openai_error": error}


@router.get("/insights")
def list_insights(db: Session = Depends(get_db)):
    rows = db.query(Insight).order_by(Insight.id).all()
    total = sum(float(r.estimated_savings) for r in rows if r.estimated_savings)
    return {
        "total_potential_savings": round(total, 2),
        "insights": [
            {
                "id": r.id,
                "type": r.type,
                "message": r.message,
                "estimated_savings": (
                    float(r.estimated_savings) if r.estimated_savings else None
                ),
            }
            for r in rows
        ],
    }