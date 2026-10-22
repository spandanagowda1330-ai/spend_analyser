from datetime import date, datetime
from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    frequency: Mapped[str] = mapped_column(String(20))
    first_seen: Mapped[date] = mapped_column(Date)
    last_charged: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="subscription")

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    raw_description: Mapped[str] = mapped_column(String(255))
    merchant: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)

    subscription: Mapped[Subscription | None] = relationship(back_populates="transactions")

class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500))
    estimated_savings: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class MerchantCategory(Base):
    __tablename__ = "merchant_categories"

    merchant: Mapped[str] = mapped_column(String(100), primary_key=True)
    category: Mapped[str] = mapped_column(String(50))