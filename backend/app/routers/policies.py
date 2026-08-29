from __future__ import annotations

import os
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.dependencies import require_admin
from app.models import ApproverContact, Policy, PolicyChunk
from app.schemas import ContactIn, ContactOut, PolicyOut
from app.services import embeddings, llm
from app.services.workflow import log_event

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.post("/upload")
async def upload_policy(
    file: UploadFile = File(...),
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files can be ingested")

    os.makedirs(settings.upload_dir, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = os.path.basename(file.filename or "policy.pdf")
    path = os.path.join(settings.upload_dir, f"{stamp}_{safe_name}")

    with open(path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    previous = (
        await db.execute(
            select(Policy).where(Policy.name == name).order_by(Policy.version.desc())
        )
    ).scalars().first()

    policy = Policy(
        name=name,
        file_path=path,
        is_active=True,
        version=(previous.version + 1) if previous else 1,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    try:
        chunk_count = await embeddings.ingest_policy(db, policy.id, path)
    except Exception as exc:  # a bad PDF should not leave a half-created policy behind
        await db.delete(policy)
        await db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not read that PDF: {exc}"
        ) from exc

    await log_event(db, "POLICY_UPLOADED", None, {"policy_id": policy.id, "chunks": chunk_count})
    await db.commit()

    return {
        "id": policy.id,
        "name": policy.name,
        "chunks": chunk_count,
        "message": "Policy ingested successfully",
    }


@router.get("/", response_model=list[PolicyOut])
async def list_policies(
    db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin)
) -> list[Policy]:
    rows = (await db.execute(select(Policy).order_by(Policy.uploaded_at.desc()))).scalars()
    return list(rows)


@router.post("/diff")
async def diff_policies(
    old_policy_id: int = Query(...),
    new_policy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
) -> dict:
    async def chunks_for(policy_id: int) -> list[str]:
        rows = (
            await db.execute(
                select(PolicyChunk.chunk_text)
                .where(PolicyChunk.policy_id == policy_id)
                .order_by(PolicyChunk.id)
            )
        ).scalars()
        return list(rows)

    old_chunks = await chunks_for(old_policy_id)
    new_chunks = await chunks_for(new_policy_id)
    if not old_chunks or not new_chunks:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One of those policies has no ingested text")

    return llm.detect_policy_diff(old_chunks, new_chunks)


@router.post("/{policy_id}/publish")
async def publish_policy(
    policy_id: int, db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin)
) -> dict:
    policy = await db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy not found")

    policy.is_active = True
    await log_event(db, "POLICY_PUBLISHED", None, {"policy_id": policy.id})
    await db.commit()
    return {"message": f"{policy.name} is now live"}


@router.get("/contacts", response_model=list[ContactOut])
async def list_contacts(
    db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin)
) -> list[ApproverContact]:
    rows = (await db.execute(select(ApproverContact).order_by(ApproverContact.id))).scalars()
    return list(rows)


@router.post("/contacts", response_model=ContactOut)
async def upsert_contact(
    body: ContactIn, db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin)
) -> ApproverContact:
    existing = (
        await db.execute(select(ApproverContact).where(ApproverContact.role == body.role))
    ).scalar_one_or_none()

    if existing:
        existing.label = body.label
        existing.email = body.email
        contact = existing
    else:
        contact = ApproverContact(role=body.role, label=body.label, email=body.email)
        db.add(contact)

    await db.commit()
    await db.refresh(contact)
    return contact
