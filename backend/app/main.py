from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import Base, engine
from . import models  # noqa: F401
from .upload import router as upload_router
from .subscriptions import router as subscriptions_router
from .categorize import router as categorize_router
from .analytics import router as analytics_router
from .insights import router as insights_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Spend Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(subscriptions_router)
app.include_router(categorize_router)
app.include_router(analytics_router)
app.include_router(insights_router)


@app.get("/health")
def health():
    return {"status": "ok"}