from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import admin, approvals, policies, requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="NIRVAH API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:3111"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(requests.router)
app.include_router(approvals.router)
app.include_router(policies.router)
app.include_router(admin.router)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "llm": "mock" if settings.use_llm_mock or not settings.gemini_api_key else "gemini",
        "email": "resend" if settings.resend_api_key else "console",
        "auth": "dev-bypass" if settings.dev_auth_bypass else "google",
    }
