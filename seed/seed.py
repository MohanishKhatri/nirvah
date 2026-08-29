"""Seed approver contacts and ingest the demo policy documents.

    python seed/seed.py            # contacts + policies
    python seed/seed.py --reset    # wipe everything first
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    ApproverContact,
    Event,
    Policy,
    PolicyChunk,
    Request,
    WorkflowNode,
)
from app.services import embeddings  # noqa: E402

POLICY_DIR = os.path.join(ROOT, "seed", "policies")

CONTACTS = [
    ("faculty_advisor", "Faculty Advisor", "faculty@nitk.edu.in"),
    ("hod", "Head of Department", "hod@nitk.edu.in"),
    ("dean", "Dean of Student Affairs", "dean@nitk.edu.in"),
    ("security", "Security Office", "security@nitk.edu.in"),
    ("venue", "Venue Office", "venues@nitk.edu.in"),
    ("finance", "Finance Office", "finance@nitk.edu.in"),
    ("registrar", "Registrar", "registrar@nitk.edu.in"),
]

# The circular is deliberately left out — it gets uploaded live during the demo.
POLICIES = [
    ("Student Activity Policy", "student_activity_policy.md"),
    ("Finance Policy", "finance_policy.md"),
    ("Security Guidelines", "security_guidelines.md"),
    ("Venue Policy", "venue_policy.md"),
]


async def reset(db) -> None:
    for model in (Event, WorkflowNode, Request, PolicyChunk, Policy, ApproverContact):
        await db.execute(delete(model))
    await db.commit()
    print("wiped: events, workflow_nodes, requests, policy_chunks, policies, approver_contacts")


async def seed_contacts(db) -> None:
    for role, label, email in CONTACTS:
        existing = (
            await db.execute(select(ApproverContact).where(ApproverContact.role == role))
        ).scalar_one_or_none()
        if existing:
            existing.label, existing.email = label, email
        else:
            db.add(ApproverContact(role=role, label=label, email=email))
    await db.commit()
    print(f"contacts seeded: {len(CONTACTS)}")


async def seed_policies(db) -> None:
    for name, filename in POLICIES:
        # prefer the PDF (what an admin actually uploads); fall back to the markdown source
        pdf_path = os.path.join(POLICY_DIR, filename[:-3] + ".pdf")
        path = pdf_path if os.path.exists(pdf_path) else os.path.join(POLICY_DIR, filename)
        if not os.path.exists(path):
            print(f"  ! missing {path}")
            continue

        policy = (
            await db.execute(select(Policy).where(Policy.name == name))
        ).scalar_one_or_none()
        if policy is None:
            policy = Policy(name=name, file_path=path, is_active=True, version=1)
            db.add(policy)
            await db.commit()
            await db.refresh(policy)
        else:
            policy.file_path, policy.is_active = path, True
            await db.commit()

        if path.lower().endswith(".pdf"):
            count = await embeddings.ingest_policy(db, policy.id, path)
        else:
            with open(path, encoding="utf-8") as handle:
                count = await embeddings.ingest_text(db, policy.id, handle.read())
        print(f"  {name}: {count} chunks")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe all data first")
    args = parser.parse_args()

    await init_db()
    async with SessionLocal() as db:
        if args.reset:
            await reset(db)
        await seed_contacts(db)
        await seed_policies(db)
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
