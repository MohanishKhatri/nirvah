from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import require_admin
from app.models import Request
from app.routers.requests import retrieval_query
from app.services import embeddings
from app.services.workflow import recompile_workflow, send_due_reminders

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/send-reminders")
async def send_reminders(
    db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin)
) -> dict:
    sent = await send_due_reminders(db)
    return {"reminders_sent": sent}


@router.post("/recompile-pending")
async def recompile_pending(
    db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin)
) -> dict:
    """Re-run the compiler over every live request against the currently published policies.

    This is what makes a newly published circular show up in workflows that already exist.
    """
    requests = list(
        (await db.execute(select(Request).where(Request.status == "pending"))).scalars()
    )

    results = []
    for request in requests:
        fields = request.structured_fields or {}
        chunks = await embeddings.search_relevant_chunks(
            db, retrieval_query(fields, request.raw_text)
        )
        outcome = await recompile_workflow(db, request, chunks)
        results.append(
            {
                "request_id": request.id,
                "purpose": fields.get("purpose", request.raw_text[:60]),
                "added": outcome["added"],
                "removed": outcome["removed"],
            }
        )

    changed = [r for r in results if r["added"] or r["removed"]]
    return {"recompiled": len(results), "changed": changed}
