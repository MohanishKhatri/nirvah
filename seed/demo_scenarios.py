"""Put the database into the exact state the demo starts from.

    python seed/demo_scenarios.py          # add both scenarios
    python seed/demo_scenarios.py --reset  # wipe requests first, then add them

Deterministic on purpose: the states are written directly rather than produced by running the
live flow, so a demo can be reset in one command.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from sqlalchemy import delete  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Event, Request, WorkflowNode  # noqa: E402
from app.services.llm_mock import compile_workflow, generate_approval_brief  # noqa: E402

STUDENT = os.getenv("DEMO_STUDENT_EMAIL", "demo.student@college.edu")

SCENARIO_1_TEXT = (
    "Our Robotics Club wants a two-day drone workshop for 120 students, Rs 35,000 funding "
    "and 3 external speakers in Seminar Hall 2."
)

SCENARIO_1_FIELDS = {
    "category": "student_event",
    "purpose": "Two-day drone workshop for 120 students",
    "budget": 35000,
    "attendees": 120,
    "external_speakers": 3,
    "venue": "Seminar Hall 2",
    "club_name": "Robotics Club",
    "duration_days": 2,
    "item_description": None,
    "missing_fields": [],
}

SCENARIO_2_TEXT = (
    "The vision lab needs to purchase a GPU server costing Rs 68,000 for deep learning research."
)

SCENARIO_2_FIELDS = {
    "category": "procurement",
    "purpose": "GPU server for the vision lab (Rs 68,000)",
    "budget": 68000,
    "attendees": None,
    "external_speakers": None,
    "venue": None,
    "club_name": None,
    "duration_days": None,
    "item_description": "GPU server for deep learning research",
    "missing_fields": [],
}


async def build(db, raw_text: str, fields: dict, approved_roles: list[str], hours_ago: int) -> int:
    created = datetime.utcnow() - timedelta(hours=hours_ago)

    request = Request(
        raw_text=raw_text,
        structured_fields=fields,
        conversation=[
            {"role": "user", "text": raw_text},
            {
                "role": "assistant",
                "text": "Which club or society is organising this?",
                "asking_for": "club_name",
            },
            {"role": "user", "text": fields.get("club_name") or "—", "answered_field": "club_name"},
        ]
        if fields.get("club_name")
        else [{"role": "user", "text": raw_text}],
        status="pending",
        submitted_by=STUDENT,
        created_at=created,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)

    compiled = compile_workflow(fields, [])
    approvals = compiled["approvals"]

    nodes: list[WorkflowNode] = []
    for approval in approvals:
        nodes.append(
            WorkflowNode(
                request_id=request.id,
                role=approval["role"],
                label=approval["label"],
                status="blocked",
                reason=approval["reason"],
                source_doc=approval["source_doc"],
                source_section=approval["source_section"],
                parallel_group=approval["parallel_group"],
                order_index=approval["order"],
                approval_token=str(uuid.uuid4()),
            )
        )
    db.add_all(nodes)
    await db.commit()

    # Mark the requested roles approved, then activate the lowest tier still blocked.
    stamp = created + timedelta(hours=1)
    for node in nodes:
        if node.role in approved_roles:
            node.status = "approved"
            node.activated_at = stamp
            stamp += timedelta(hours=1)
            node.completed_at = stamp

    remaining = [n for n in nodes if n.status == "blocked"]
    if remaining:
        tier = min(n.order_index for n in remaining)
        for node in remaining:
            if node.order_index == tier:
                node.status = "active"
                node.activated_at = stamp

    # Written directly rather than sent, but the content should still be there for the student
    # to see — same as a real activation would generate.
    approved_labels = [n.label for n in nodes if n.status == "approved"]
    for node in nodes:
        if node.status in ("approved", "active"):
            completed_before = [label for label in approved_labels if label != node.label]
            node.email_brief = generate_approval_brief(
                node.label, fields, completed_before, node.reason, node.source_doc, node.source_section
            )

    db.add(Event(request_id=request.id, event_type="WORKFLOW_COMPILED", payload={"seeded": True}))
    await db.commit()

    chain = " -> ".join(f"{n.label}[{n.status}]" for n in nodes)
    print(f"  #{request.id}: {chain}")
    return request.id


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete existing requests first")
    args = parser.parse_args()

    await init_db()
    async with SessionLocal() as db:
        if args.reset:
            await db.execute(delete(Event).where(Event.request_id.is_not(None)))
            await db.execute(delete(WorkflowNode))
            await db.execute(delete(Request))
            await db.commit()
            print("existing requests cleared")

        print("Scenario 1 — Robotics Club workshop, mid-flight:")
        await build(db, SCENARIO_1_TEXT, SCENARIO_1_FIELDS, ["faculty_advisor", "hod"], hours_ago=26)

        print("Scenario 2 — GPU procurement, ready for the circular:")
        await build(db, SCENARIO_2_TEXT, SCENARIO_2_FIELDS, [], hours_ago=6)

    print("done — approver contacts come from seed/seed.py")


if __name__ == "__main__":
    asyncio.run(main())
