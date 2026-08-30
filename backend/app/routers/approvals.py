from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Request, WorkflowNode
from app.schemas import RejectionIn
from app.services.workflow import approve_node, reject_node

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


async def _node_for_token(db: AsyncSession, token: str) -> WorkflowNode:
    node = (
        await db.execute(select(WorkflowNode).where(WorkflowNode.approval_token == token))
    ).scalar_one_or_none()
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This approval link is not valid")
    return node


@router.get("/action")
async def approval_action(
    token: str = Query(...),
    action: str = Query("approve", pattern="^(approve|reject)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The email link lands here. The UUID token is the only credential.

    Neither branch mutates anything — a GET must stay side-effect-free, since email clients and
    link-scanning gateways prefetch links before a human ever looks at them. Both approve and
    reject hand back what the confirm screen needs and wait for an explicit POST.
    """
    node = await _node_for_token(db, token)

    if node.status == "approved":
        return {"message": "This request has already been approved"}
    if node.status == "rejected":
        return {"message": "This request has already been rejected"}
    if node.status == "blocked":
        return {"message": "This approval is not active yet — earlier approvers have not responded"}

    request = await db.get(Request, node.request_id)
    purpose = (request.structured_fields or {}).get("purpose", "") if request else ""

    if action == "reject":
        return {
            "requires_reason": True,
            "token": token,
            "label": node.label,
            "purpose": purpose,
        }

    return {
        "requires_confirmation": True,
        "token": token,
        "label": node.label,
        "purpose": purpose,
    }


@router.post("/confirm")
async def confirm_approval(
    token: str = Query(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """The explicit confirm step for approval — the only place that actually mutates."""
    node = await _node_for_token(db, token)

    if node.status == "approved":
        return {"message": "This request has already been approved"}
    if node.status == "rejected":
        return {"message": "This request has already been rejected"}
    if node.status == "blocked":
        return {"message": "This approval is not active yet — earlier approvers have not responded"}

    await approve_node(db, node)
    return {"message": "Approved successfully. Thank you."}


@router.post("/reject")
async def submit_rejection(
    body: RejectionIn,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    node = await _node_for_token(db, token)

    if node.status in {"approved", "rejected"}:
        return {"message": f"This request has already been {node.status}"}

    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A reason is required")

    await reject_node(db, node, reason)
    return {"message": "Rejection recorded. Applicant has been notified."}
