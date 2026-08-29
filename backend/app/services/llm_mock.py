"""Deterministic stand-ins for the Gemini calls.

Used when ``USE_LLM_MOCK=true`` or no ``GEMINI_API_KEY`` is set. The rules here mirror the
four demo policy documents, so the whole product is demoable with no API key at all.
"""

from __future__ import annotations

import re

CATEGORY_REQUIRED_FIELDS: dict[str, list[str]] = {
    "student_event": ["purpose", "club_name", "budget", "attendees", "venue"],
    "procurement": ["purpose", "budget", "item_description"],
    "course_action": ["purpose"],
    "travel": ["purpose", "budget", "attendees"],
    "facility_booking": ["purpose", "venue", "attendees"],
    "other": ["purpose", "budget"],
}

_NUM = r"(?:₹|rs\.?|inr)?\s*([\d][\d,]*(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|cr|crore)?"


def _to_number(value: str, unit: str | None) -> float:
    amount = float(value.replace(",", ""))
    unit = (unit or "").lower()
    if unit in {"k", "thousand"}:
        amount *= 1_000
    elif unit in {"lakh", "lakhs"}:
        amount *= 100_000
    elif unit in {"cr", "crore"}:
        amount *= 10_000_000
    return amount


def _guess_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("buy", "purchase", "procure", "procurement", "gpu", "equipment", "laptop")):
        return "procurement"
    if any(w in t for w in ("workshop", "event", "fest", "seminar", "hackathon", "club", "competition")):
        return "student_event"
    if any(w in t for w in ("travel", "trip", "industrial visit", "conference")):
        return "travel"
    if any(w in t for w in ("book", "booking", "hall", "auditorium")) and "event" not in t:
        return "facility_booking"
    if any(w in t for w in ("course", "credit", "elective", "drop", "registration")):
        return "course_action"
    return "other"


def extract_intent(request_text: str) -> dict:
    text = request_text.strip()
    lower = text.lower()
    category = _guess_category(lower)

    fields: dict = {
        "category": category,
        "purpose": text[:200],
        "budget": None,
        "attendees": None,
        "external_speakers": None,
        "venue": None,
        "club_name": None,
        "duration_days": None,
        "item_description": None,
        "missing_fields": [],
    }

    money = re.search(r"(?:₹|rs\.?|inr)\s*" + _NUM, lower) or re.search(
        _NUM + r"\s*(?:rupees|budget|funding)", lower
    )
    if money:
        fields["budget"] = _to_number(money.group(1), money.group(2))

    people = re.search(r"(\d+)\s*(?:students|participants|attendees|people)", lower)
    if people:
        fields["attendees"] = int(people.group(1))

    speakers = re.search(r"(\d+)\s*(?:external\s+)?(?:speakers|guests|experts)", lower)
    if speakers:
        fields["external_speakers"] = int(speakers.group(1))

    club = re.search(r"([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*)\s+(?i:club|society|chapter|cell)", text)
    if club:
        words = [w for w in club.group(1).split() if w.lower() not in {"our", "the", "my", "a"}]
        if words:
            fields["club_name"] = " ".join(words) + " Club"

    venue = re.search(
        r"(?:in|at)\s+((?:seminar hall|lecture hall|auditorium|room|hall|lab)\s*[\w\d-]*)", lower
    )
    if venue:
        fields["venue"] = venue.group(1).strip().title()

    days = re.search(r"(\d+)[- ]day", lower)
    if days:
        fields["duration_days"] = int(days.group(1))
    elif "two-day" in lower or "two day" in lower:
        fields["duration_days"] = 2
    elif "one-day" in lower or "single day" in lower:
        fields["duration_days"] = 1

    if category == "procurement":
        item = re.search(r"(?:buy|purchase|procure)\s+(?:a\s+|an\s+|some\s+)?([\w\s-]{3,60})", lower)
        if item:
            fields["item_description"] = item.group(1).strip()

    required = CATEGORY_REQUIRED_FIELDS.get(category, CATEGORY_REQUIRED_FIELDS["other"])
    fields["missing_fields"] = [f for f in required if not fields.get(f)]
    return fields


_QUESTIONS = {
    "club_name": "Which club or society is organising this?",
    "budget": "Roughly what budget are you asking for, in rupees?",
    "attendees": "How many people do you expect to attend?",
    "venue": "Where would you like to hold it? Give me the venue or hall name.",
    "external_speakers": "Will any external speakers or guests be attending? How many?",
    "duration_days": "How many days will this run for?",
    "item_description": "What exactly are you looking to purchase?",
    "purpose": "In one line, what is this request for?",
}


def generate_followup_question(request_text: str, missing_field: str) -> str:
    return _QUESTIONS.get(
        missing_field, f"Could you provide your {missing_field.replace('_', ' ')}?"
    )


_AMOUNT_RE = re.compile(r"(?:₹|rs\.?)\s*([\d][\d,]*)", re.IGNORECASE)


def _find_registrar_rule(chunks: list[dict]) -> dict | None:
    """Look for a 'purchases above X require Registrar approval' clause in the retrieved text."""
    for chunk in chunks:
        text = (chunk.get("chunk_text") or "").lower()
        if "registrar" not in text or "approval" not in text:
            continue
        amounts = [int(a.replace(",", "")) for a in _AMOUNT_RE.findall(text)]
        if not amounts:
            continue
        return {
            "threshold": min(amounts),
            "source_doc": chunk.get("policy_name") or "Finance Circular",
            "source_section": chunk.get("source_section"),
        }
    return None


def _approval(role, label, reason, doc, section, order, group=None) -> dict:
    return {
        "role": role,
        "label": label,
        "reason": reason,
        "source_doc": doc,
        "source_section": section,
        "parallel_group": group,
        "order": order,
    }


def compile_workflow(structured_fields: dict, retrieved_chunks: list[dict] | None = None) -> dict:
    """Rule-based mirror of the four demo policies."""
    category = structured_fields.get("category", "other")
    budget = structured_fields.get("budget") or 0
    attendees = structured_fields.get("attendees") or 0
    speakers = structured_fields.get("external_speakers") or 0
    venue = (structured_fields.get("venue") or "").lower()

    approvals: list[dict] = []
    blocks: list[str] = []
    missing_docs: list[str] = []

    if "seminar hall 2" in venue and attendees > 200:
        blocks.append(
            f"Seminar Hall 2 has a maximum capacity of 200; {attendees} attendees requested "
            "— Venue Policy §2.4"
        )

    if category in {"student_event", "facility_booking", "travel"}:
        approvals.append(
            _approval(
                "faculty_advisor",
                "Faculty Advisor",
                "All student club events require Faculty Advisor approval before escalation.",
                "Student Activity Policy",
                "§3",
                1,
            )
        )
        approvals.append(
            _approval(
                "hod",
                "Head of Department",
                "Faculty Advisor approval is followed by Head of Department approval.",
                "Student Activity Policy",
                "§3",
                2,
            )
        )
    else:
        approvals.append(
            _approval(
                "hod",
                "Head of Department",
                "Departmental requests are initiated through the Head of Department.",
                "Student Activity Policy",
                "§3",
                2,
            )
        )

    tier3: list[dict] = []
    if speakers:
        tier3.append(
            _approval(
                "security",
                "Security Office",
                f"{speakers} external speaker(s) attending — events with external guests require "
                "Security Office clearance.",
                "Security Guidelines",
                "§4.1",
                3,
                "clearances",
            )
        )
        missing_docs.append("Identity details of each external guest")
    if attendees and attendees > 100:
        tier3.append(
            _approval(
                "venue",
                "Venue Office",
                f"{attendees} attendees exceeds the 100-attendee threshold for Venue Office approval.",
                "Venue Policy",
                "§2.3",
                3,
                "clearances",
            )
        )
    if len(tier3) == 1:
        tier3[0]["parallel_group"] = None
    approvals.extend(tier3)

    if budget:
        approvals.append(
            _approval(
                "finance",
                "Finance Office",
                f"Request involves expenditure of ₹{int(budget):,} and must route through the "
                "Finance Office.",
                "Finance Policy",
                "§5.1",
                4,
            )
        )
    if budget and budget > 25_000:
        approvals.append(
            _approval(
                "dean",
                "Dean of Student Affairs",
                f"Budget ₹{int(budget):,} exceeds the ₹25,000 threshold for "
                f"{'procurement' if category == 'procurement' else 'student activity expenditure'}.",
                "Finance Policy",
                "§8.3" if category == "procurement" else "§8.2",
                5,
            )
        )
    if category == "procurement" and budget and budget > 50_000:
        missing_docs.append("Three vendor quotations (Finance Policy §9.1)")

    # Rules that only exist once a circular has been ingested are read off the retrieved text,
    # so uploading Finance Circular 14/2026 visibly adds a Registrar node on recompile.
    registrar_rule = _find_registrar_rule(retrieved_chunks or [])
    if registrar_rule and budget and budget > registrar_rule["threshold"]:
        approvals.append(
            _approval(
                "registrar",
                "Registrar",
                f"Purchase of ₹{int(budget):,} exceeds the ₹{registrar_rule['threshold']:,} "
                "threshold introduced for Registrar approval.",
                registrar_rule["source_doc"],
                registrar_rule["source_section"],
                6,
            )
        )

    if structured_fields.get("duration_days") and structured_fields["duration_days"] > 1:
        missing_docs.append("Additional documentation for multi-day events (Student Activity Policy §5)")

    if blocks:
        return {"approvals": [], "missing_docs": missing_docs, "immediate_blocks": blocks}

    return {"approvals": approvals, "missing_docs": missing_docs, "immediate_blocks": []}


def generate_approval_brief(
    label: str,
    structured_fields: dict,
    completed_approvals: list[str],
    reason: str,
    source_doc: str,
    source_section: str | None = None,
) -> str:
    purpose = structured_fields.get("purpose", "a student request")
    budget = structured_fields.get("budget")
    attendees = structured_fields.get("attendees")

    parts = [f"A student has submitted a request for {purpose}."]
    detail = []
    if budget:
        detail.append(f"a budget of ₹{int(budget):,}")
    if attendees:
        detail.append(f"{attendees} expected attendees")
    if structured_fields.get("venue"):
        detail.append(f"venue {structured_fields['venue']}")
    if detail:
        parts.append("It involves " + ", ".join(detail) + ".")

    if completed_approvals:
        parts.append("Already approved by " + ", ".join(completed_approvals) + ".")
    else:
        parts.append("This is the first approval in the chain.")

    citation = f"{source_doc} {source_section}".strip()
    parts.append(f"It is on your desk as {label} because {reason.rstrip('.')} ({citation}).")
    parts.append("You can approve or reject directly from this email — no login is required.")
    return " ".join(parts)


AUTHORITIES = [
    ("registrar", "Registrar"),
    ("dean of student affairs", "Dean of Student Affairs"),
    ("dean", "Dean of Student Affairs"),
    ("head of department", "Head of Department"),
    ("finance office", "Finance Office"),
    ("security office", "Security Office"),
    ("venue office", "Venue Office"),
    ("faculty advisor", "Faculty Advisor"),
]

_RULE_RE = re.compile(r"[^.\n]*\b(?:require|requires|shall)\b[^.\n]*\.", re.IGNORECASE)


def _rules(chunks: list[str]) -> dict[tuple[str, int], str]:
    """Map (approving authority, threshold) → the sentence that states it."""
    found: dict[tuple[str, int], str] = {}
    for chunk in chunks:
        # PDF text wraps mid-sentence, so flatten whitespace before matching sentences
        for sentence in _RULE_RE.findall(" ".join(chunk.split())):
            lowered = sentence.lower()
            authority = next((label for key, label in AUTHORITIES if key in lowered), None)
            if authority is None:
                continue
            amounts = [int(a.replace(",", "")) for a in _AMOUNT_RE.findall(sentence)]
            threshold = max(amounts) if amounts else 0
            # section numbers such as "3.1" split the sentence, so trim any leading digits
            text = " ".join(sentence.split()).lstrip("0123456789. ")
            found.setdefault((authority, threshold), text)
    return found


def detect_policy_diff(old_chunks: list[str], new_chunks: list[str]) -> dict:
    """Compare the approval rules each version states, ignoring wording and formatting."""
    old_rules = _rules(old_chunks[:20])
    new_rules = _rules(new_chunks[:20])

    changed, added, removed = [], [], []

    for (authority, threshold), sentence in new_rules.items():
        if (authority, threshold) in old_rules:
            continue
        prior = [(a, t) for (a, t) in old_rules if a == authority]
        if prior and threshold:
            old_authority, old_threshold = prior[0]
            changed.append(
                {
                    "description": f"{authority} approval threshold changed",
                    "old_text": old_rules[(old_authority, old_threshold)],
                    "new_text": sentence,
                    "impact": (
                        f"Requests above ₹{threshold:,} now require {authority} approval "
                        f"(previously ₹{old_threshold:,})."
                    ),
                }
            )
        else:
            impact = (
                f"Requests above ₹{threshold:,} gain a {authority} approval node."
                if threshold
                else f"Affected requests gain a {authority} approval node."
            )
            added.append(
                {
                    "description": f"New rule requiring {authority} approval",
                    "text": sentence,
                    "impact": impact,
                }
            )

    # A circular amends rather than replaces, so absent rules are not removals. Only treat the
    # new document as a full replacement when it states at least as many rules as the old one.
    if len(new_rules) >= len(old_rules):
        for (authority, threshold), sentence in old_rules.items():
            if (authority, threshold) in new_rules or any(a == authority for a, _ in new_rules):
                continue
            removed.append(
                {
                    "description": f"{authority} rule no longer stated",
                    "text": sentence,
                    "impact": f"{authority} approval may no longer be required.",
                }
            )

    return {"changed": changed[:5], "added": added[:5], "removed": removed[:5]}
