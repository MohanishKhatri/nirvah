"""Workflow state machine: compile a request into nodes, then walk the tiers as approvals land."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ApproverContact, Event, Request, WorkflowNode
from app.services import email as email_service
from app.services import llm

logger = logging.getLogger(__name__)


async def log_event(
    db: AsyncSession, event_type: str, request_id: int | None = None, payload: dict | None = None
) -> None:
    db.add(Event(request_id=request_id, event_type=event_type, payload=payload or {}))


async def _contact_for(db: AsyncSession, role: str) -> ApproverContact | None:
    return (
        await db.execute(select(ApproverContact).where(ApproverContact.role == role))
    ).scalar_one_or_none()


async def compile_and_store_workflow(
    db: AsyncSession, request: Request, retrieved_chunks: list[dict]
) -> dict:
    """Returns the compiled workflow dict so the router can shape its response."""
    compiled = llm.compile_workflow(request.structured_fields or {}, retrieved_chunks)
    blocks = compiled.get("immediate_blocks") or []

    if blocks:
        request.status = "rejected"
        request.rejection_reason = "; ".join(blocks)
        await log_event(db, "WORKFLOW_COMPILED", request.id, {"immediate_blocks": blocks})
        await db.commit()
        return compiled

    for approval in compiled.get("approvals", []):
        contact = await _contact_for(db, approval["role"])
        db.add(
            WorkflowNode(
                request_id=request.id,
                role=approval["role"],
                label=approval.get("label") or (contact.label if contact else approval["role"]),
                status="blocked",
                reason=approval.get("reason", ""),
                source_doc=approval.get("source_doc", ""),
                source_section=approval.get("source_section"),
                parallel_group=approval.get("parallel_group"),
                order_index=int(approval.get("order", 1)),
                approval_token=str(uuid.uuid4()),
            )
        )

    request.status = "pending"
    await log_event(
        db,
        "WORKFLOW_COMPILED",
        request.id,
        {"node_count": len(compiled.get("approvals", [])), "missing_docs": compiled.get("missing_docs", [])},
    )
    await db.commit()

    await activate_next_nodes(db, request.id)
    return compiled


async def recompile_workflow(
    db: AsyncSession, request: Request, retrieved_chunks: list[dict]
) -> dict:
    """Re-run the compiler over a live request after a policy change.

    Approvals already given are kept — an approver never has to sign twice. Nodes the new
    policy no longer justifies are dropped only while they are still blocked.
    """
    compiled = llm.compile_workflow(request.structured_fields or {}, retrieved_chunks)
    approvals = compiled.get("approvals", [])
    if compiled.get("immediate_blocks") or not approvals:
        return {"added": [], "removed": [], "unchanged": True}

    existing = {n.role: n for n in await _nodes_for(db, request.id)}
    new_roles = {a["role"] for a in approvals}

    added: list[str] = []
    for approval in approvals:
        node = existing.get(approval["role"])
        if node is None:
            contact = await _contact_for(db, approval["role"])
            db.add(
                WorkflowNode(
                    request_id=request.id,
                    role=approval["role"],
                    label=approval.get("label") or (contact.label if contact else approval["role"]),
                    status="blocked",
                    reason=approval.get("reason", ""),
                    source_doc=approval.get("source_doc", ""),
                    source_section=approval.get("source_section"),
                    parallel_group=approval.get("parallel_group"),
                    order_index=int(approval.get("order", 1)),
                    approval_token=str(uuid.uuid4()),
                )
            )
            added.append(approval["role"])
        elif node.status == "blocked":
            # not yet reached, so the new wording and ordering can be applied safely
            node.reason = approval.get("reason", node.reason)
            node.source_doc = approval.get("source_doc", node.source_doc)
            node.source_section = approval.get("source_section")
            node.parallel_group = approval.get("parallel_group")
            node.order_index = int(approval.get("order", node.order_index))

    removed: list[str] = []
    for role, node in existing.items():
        if role not in new_roles and node.status == "blocked":
            await db.delete(node)
            removed.append(role)

    if request.status in {"approved", "rejected"} and (added or removed):
        request.status = "pending"

    await log_event(
        db, "WORKFLOW_COMPILED", request.id, {"recompiled": True, "added": added, "removed": removed}
    )
    await db.commit()

    await activate_next_nodes(db, request.id)
    return {"added": added, "removed": removed, "unchanged": not (added or removed)}


async def _nodes_for(db: AsyncSession, request_id: int) -> list[WorkflowNode]:
    return list(
        (
            await db.execute(
                select(WorkflowNode)
                .where(WorkflowNode.request_id == request_id)
                .order_by(WorkflowNode.order_index, WorkflowNode.id)
            )
        ).scalars()
    )


async def _send_node_email(
    db: AsyncSession, request: Request, node: WorkflowNode, completed_labels: list[str]
) -> None:
    contact = await _contact_for(db, node.role)
    if contact is None:
        logger.warning("No approver contact for role %r — email skipped", node.role)
        return

    brief = llm.generate_approval_brief(
        node.label,
        request.structured_fields or {},
        completed_labels,
        node.reason,
        node.source_doc,
        node.source_section,
    )
    node.email_brief = brief
    await db.commit()
    await email_service.send_approval_email(
        contact.email, node.approval_token, node.label, brief, request.structured_fields or {}
    )


async def activate_next_nodes(db: AsyncSession, request_id: int) -> None:
    """Activate every blocked node in the lowest remaining tier. Same tier = runs in parallel."""
    request = await db.get(Request, request_id)
    if request is None:
        return

    nodes = await _nodes_for(db, request_id)
    if not nodes:
        return

    if any(n.status == "rejected" for n in nodes):
        return

    blocked = [n for n in nodes if n.status == "blocked"]
    active = [n for n in nodes if n.status == "active"]

    if active:
        return  # current tier has not cleared yet

    if not blocked:
        request.status = "approved"
        await log_event(db, "REQUEST_APPROVED", request_id, {})
        await db.commit()
        await email_service.send_approval_notification(
            request.submitted_by, (request.structured_fields or {}).get("purpose", "your request")
        )
        return

    tier = min(n.order_index for n in blocked)
    completed_labels = [n.label for n in nodes if n.status == "approved"]
    now = datetime.utcnow()

    to_notify = []
    for node in blocked:
        if node.order_index != tier:
            continue
        node.status = "active"
        node.activated_at = now
        await log_event(db, "NODE_ACTIVATED", request_id, {"node_id": node.id, "role": node.role})
        to_notify.append(node)

    await db.commit()

    for node in to_notify:
        await _send_node_email(db, request, node, completed_labels)


async def approve_node(db: AsyncSession, node: WorkflowNode) -> None:
    node.status = "approved"
    node.completed_at = datetime.utcnow()
    await log_event(db, "NODE_APPROVED", node.request_id, {"node_id": node.id, "role": node.role})
    await db.commit()
    await activate_next_nodes(db, node.request_id)


async def reject_node(db: AsyncSession, node: WorkflowNode, reason: str) -> None:
    node.status = "rejected"
    node.rejection_reason = reason
    node.completed_at = datetime.utcnow()

    request = await db.get(Request, node.request_id)
    if request is not None:
        request.status = "rejected"
        request.rejection_reason = reason

    await log_event(
        db,
        "NODE_REJECTED",
        node.request_id,
        {"node_id": node.id, "role": node.role, "reason": reason},
    )
    await log_event(db, "REQUEST_REJECTED", node.request_id, {"reason": reason})
    await db.commit()

    if request is not None:
        await email_service.send_rejection_notification(
            request.submitted_by,
            (request.structured_fields or {}).get("purpose", "your request"),
            node.label,
            reason,
        )


async def send_due_reminders(db: AsyncSession) -> int:
    """Nudge approvers who have been sitting on an active node past the reminder window."""
    cutoff = datetime.utcnow() - timedelta(hours=settings.reminder_after_hours)
    nodes = list(
        (
            await db.execute(
                select(WorkflowNode).where(
                    WorkflowNode.status == "active",
                    WorkflowNode.activated_at.is_not(None),
                    WorkflowNode.activated_at < cutoff,
                    WorkflowNode.reminder_sent_at.is_(None),
                )
            )
        ).scalars()
    )

    sent = 0
    for node in nodes:
        request = await db.get(Request, node.request_id)
        contact = await _contact_for(db, node.role)
        if request is None or contact is None:
            continue
        brief = llm.generate_approval_brief(
            node.label,
            request.structured_fields or {},
            [n.label for n in await _nodes_for(db, request.id) if n.status == "approved"],
            node.reason,
            node.source_doc,
            node.source_section,
        )
        await email_service.send_reminder_email(
            contact.email, node.approval_token, node.label, brief, request.structured_fields or {}
        )
        node.email_brief = brief
        node.reminder_sent_at = datetime.utcnow()
        await log_event(db, "REMINDER_SENT", request.id, {"node_id": node.id})
        sent += 1

    await db.commit()
    return sent
