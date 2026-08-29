from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Request, WorkflowNode
from app.schemas import AnswerIn, NodeOut, RequestCreate, RequestSummaryOut, SubmitResponse, WorkflowOut
from app.services import embeddings, llm
from app.services.workflow import compile_and_store_workflow, log_event

router = APIRouter(prefix="/api/requests", tags=["requests"])


def retrieval_query(fields: dict, raw_text: str) -> str:
    """Bias retrieval toward the clauses that decide the chain: money, headcount, venue, guests."""
    parts = [raw_text]
    if fields.get("category"):
        parts.append(f"category {fields['category']}")
    if fields.get("budget"):
        parts.append(f"expenditure approval threshold budget {int(fields['budget'])}")
    if fields.get("attendees"):
        parts.append(f"venue approval attendees capacity {fields['attendees']}")
    if fields.get("external_speakers"):
        parts.append("external speakers guests security clearance")
    if fields.get("venue"):
        parts.append(f"venue booking {fields['venue']}")
    if fields.get("duration_days") and fields["duration_days"] > 1:
        parts.append("multi-day event documentation")
    return " ".join(parts)


async def _advance(db: AsyncSession, request: Request) -> SubmitResponse:
    """Either ask for the next missing field, or compile the workflow."""
    fields = dict(request.structured_fields or {})
    missing = [f for f in (fields.get("missing_fields") or []) if not fields.get(f)]
    fields["missing_fields"] = missing
    request.structured_fields = fields

    if missing:
        question = llm.generate_followup_question(request.raw_text, missing[0])
        conversation = list(request.conversation or [])
        conversation.append({"role": "assistant", "text": question, "asking_for": missing[0]})
        request.conversation = conversation
        request.status = "awaiting_info"
        await log_event(db, "QUESTION_ASKED", request.id, {"field": missing[0]})
        await db.commit()
        return SubmitResponse(
            request_id=request.id,
            status="awaiting_info",
            question=question,
            asking_for=missing[0],
            fields_extracted={k: v for k, v in fields.items() if k != "missing_fields" and v},
        )

    request.status = "compiling"
    await db.commit()

    chunks = await embeddings.search_relevant_chunks(db, retrieval_query(fields, request.raw_text))
    compiled = await compile_and_store_workflow(db, request, chunks)
    blocks = compiled.get("immediate_blocks") or []

    return SubmitResponse(
        request_id=request.id,
        status=request.status,
        workflow_compiled=not blocks,
        immediate_blocks=blocks,
    )


@router.post("/", response_model=SubmitResponse)
async def create_request(
    body: RequestCreate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> SubmitResponse:
    fields = llm.extract_intent(body.text)

    request = Request(
        raw_text=body.text,
        structured_fields=fields,
        conversation=[{"role": "user", "text": body.text}],
        status="draft",
        submitted_by=user,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)

    await log_event(db, "REQUEST_CREATED", request.id, {"category": fields.get("category")})
    await db.commit()

    return await _advance(db, request)


async def _owned_request(db: AsyncSession, request_id: int, user: str) -> Request:
    request = await db.get(Request, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if request.submitted_by != user:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This request belongs to someone else")
    return request


def _coerce(value: str):
    text = value.strip()
    cleaned = text.replace(",", "").replace("₹", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return text


@router.post("/{request_id}/answer", response_model=SubmitResponse)
async def answer_question(
    request_id: int,
    body: AnswerIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> SubmitResponse:
    request = await _owned_request(db, request_id, user)

    fields = dict(request.structured_fields or {})
    fields[body.field] = _coerce(body.value)
    fields["missing_fields"] = [f for f in (fields.get("missing_fields") or []) if f != body.field]
    request.structured_fields = fields

    conversation = list(request.conversation or [])
    conversation.append({"role": "user", "text": body.value, "answered_field": body.field})
    request.conversation = conversation

    await log_event(db, "ANSWER_GIVEN", request.id, {"field": body.field})
    await db.commit()

    return await _advance(db, request)


@router.get("/", response_model=list[RequestSummaryOut])
async def list_requests(
    db: AsyncSession = Depends(get_db), user: str = Depends(get_current_user)
) -> list[RequestSummaryOut]:
    rows = (
        await db.execute(
            select(Request).where(Request.submitted_by == user).order_by(Request.created_at.desc())
        )
    ).scalars()

    return [
        RequestSummaryOut(
            id=r.id,
            purpose=(r.structured_fields or {}).get("purpose") or r.raw_text[:80],
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{request_id}/workflow", response_model=WorkflowOut)
async def get_workflow(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> WorkflowOut:
    request = await _owned_request(db, request_id, user)

    nodes = (
        await db.execute(
            select(WorkflowNode)
            .where(WorkflowNode.request_id == request_id)
            .order_by(WorkflowNode.order_index, WorkflowNode.id)
        )
    ).scalars()

    return WorkflowOut(
        request_id=request.id,
        status=request.status,
        structured_fields=request.structured_fields or {},
        conversation=request.conversation or [],
        nodes=[NodeOut.model_validate(n, from_attributes=True) for n in nodes],
    )
