from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import CORS_ALLOWED_ORIGINS
from .routes import health, uploads, documents

app = FastAPI(title="Ledger Lift API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(uploads.router)
app.include_router(documents.router)
