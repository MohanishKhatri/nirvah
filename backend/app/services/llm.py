"""Gemini calls. Every function degrades to a deterministic fallback rather than raising."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.services import llm_mock

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-1.5-flash"

CATEGORIES = [
    "student_event",
    "procurement",
    "course_action",
    "travel",
    "facility_booking",
    "other",
]

_model = None


def _live() -> bool:
    return bool(settings.gemini_api_key) and not settings.use_llm_mock


def _get_model():
    global _model
    if _model is None:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(MODEL_NAME)
    return _model


def _generate(prompt: str) -> str:
    return _get_model().generate_content(prompt).text or ""


def parse_json(text: str) -> Any:
    """Gemini wraps JSON in markdown fences even when told not to. Strip them, then parse."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def _chunk_block(chunks: list[dict], limit: int = 8) -> str:
    lines = []
    for c in chunks[:limit]:
        header = c.get("policy_name", "Policy")
        section = c.get("source_section")
        if section:
            header = f"{header} {section}"
        lines.append(f"[{header}]\n{c.get('chunk_text', '')}")
    return "\n\n".join(lines)


# ------------------------------------------------------------------ 1. intent

def extract_intent(request_text: str) -> dict:
    if not _live():
        return llm_mock.extract_intent(request_text)

    prompt = f"""You extract structured data from a student's request to their institution.

Return ONLY a JSON object, no markdown fences and no explanation, with exactly these keys:
{{
  "category": one of {CATEGORIES},
  "purpose": one-line summary,
  "budget": number or null,
  "attendees": number or null,
  "external_speakers": number or null,
  "venue": string or null,
  "club_name": string or null,
  "duration_days": number or null,
  "item_description": string or null,
  "missing_fields": array of field names
}}

"missing_fields" must list the fields that a request of THIS category would normally need
but that the text does not state. Judge by category: a student_event needs club_name, budget,
attendees and venue; a procurement needs item_description and budget; a course_action needs
little beyond purpose. Never list a field you already filled in.

Amounts may be written as "35k", "₹35,000" or "1.5 lakh" — normalise them to plain numbers.

Student request:
\"\"\"{request_text}\"\"\""""

    try:
        data = parse_json(_generate(prompt))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
        data.setdefault("category", "other")
        data.setdefault("purpose", request_text[:200])
        data.setdefault("missing_fields", [])
        return data
    except Exception:
        logger.exception("extract_intent failed; falling back")
        fallback = llm_mock.extract_intent(request_text)
        return fallback


# ---------------------------------------------------------------- 2. question

def generate_followup_question(request_text: str, missing_field: str) -> str:
    if not _live():
        return llm_mock.generate_followup_question(request_text, missing_field)

    prompt = f"""A student submitted this request to their institution:
\"\"\"{request_text}\"\"\"

One piece of information is missing: "{missing_field}".

Write ONE short question asking for it. Sound like a helpful person, not a form label.
Return only the question text — no quotes, no preamble."""

    try:
        text = _generate(prompt).strip().strip('"')
        return text or llm_mock.generate_followup_question(request_text, missing_field)
    except Exception:
        logger.exception("generate_followup_question failed; falling back")
        return f"Could you provide your {missing_field.replace('_', ' ')}?"


# ---------------------------------------------------------------- 3. workflow

def compile_workflow(structured_fields: dict, retrieved_chunks: list[dict]) -> dict:
    if not _live() or not retrieved_chunks:
        return llm_mock.compile_workflow(structured_fields, retrieved_chunks)

    prompt = f"""You are a policy compiler. Given a student request and excerpts from the
institution's policy documents, produce the exact approval chain the policies require.

REQUEST (JSON):
{json.dumps(structured_fields, indent=2, ensure_ascii=False)}

POLICY EXCERPTS:
{_chunk_block(retrieved_chunks)}

Return ONLY this JSON object, no markdown fences:
{{
  "approvals": [
    {{
      "role": "dean | hod | security | venue | finance | registrar | faculty_advisor",
      "label": "Dean of Student Affairs",
      "reason": "Budget Rs 35,000 exceeds the Rs 25,000 threshold",
      "source_doc": "Finance Policy",
      "source_section": "8.2",
      "parallel_group": "clearances" or null,
      "order": 5
    }}
  ],
  "missing_docs": ["documents the applicant must still upload"],
  "immediate_blocks": ["policy violations that make the request impossible"]
}}

Rules:
- Only create an approval that is explicitly supported by the provided policy text. If no
  policy justifies an approval, do not create it. Never invent an approver.
- Every approval MUST have a non-empty reason and source_doc, and a source_section when the
  excerpt shows one. The reason must quote the specific number or condition that triggered it.
- "order" controls sequence: lower runs earlier. Two approvals that do not depend on each other
  share the same "order" AND the same "parallel_group" name.
- If a policy states an outright limit the request violates (for example a hall capacity smaller
  than the attendee count), put that in "immediate_blocks" and return an empty "approvals" list."""

    try:
        data = parse_json(_generate(prompt))
        approvals = data.get("approvals") or []
        cleaned = []
        for i, a in enumerate(approvals):
            if not a.get("role") or not a.get("source_doc"):
                continue
            cleaned.append(
                {
                    "role": str(a["role"]).strip().lower().replace(" ", "_"),
                    "label": a.get("label") or str(a["role"]).replace("_", " ").title(),
                    "reason": a.get("reason") or "Required by institutional policy.",
                    "source_doc": a["source_doc"],
                    "source_section": a.get("source_section"),
                    "parallel_group": a.get("parallel_group"),
                    "order": int(a.get("order") or i + 1),
                }
            )
        if not cleaned and not data.get("immediate_blocks"):
            raise ValueError("no usable approvals returned")
        return {
            "approvals": cleaned,
            "missing_docs": data.get("missing_docs") or [],
            "immediate_blocks": data.get("immediate_blocks") or [],
        }
    except Exception:
        logger.exception("compile_workflow failed; falling back to rule-based compiler")
        return llm_mock.compile_workflow(structured_fields, retrieved_chunks)


# ------------------------------------------------------------------- 4. brief

def generate_approval_brief(
    label: str,
    structured_fields: dict,
    completed_approvals: list[str],
    reason: str,
    source_doc: str,
    source_section: str | None = None,
) -> str:
    if not _live():
        return llm_mock.generate_approval_brief(
            label, structured_fields, completed_approvals, reason, source_doc, source_section
        )

    citation = f"{source_doc} {source_section or ''}".strip()
    prompt = f"""Write a 4-6 sentence plain-text paragraph for an approval email.

Recipient role: {label}
Request details (JSON): {json.dumps(structured_fields, ensure_ascii=False)}
Already approved by: {', '.join(completed_approvals) or 'nobody yet — this is the first step'}
Why it needs this approver: {reason}
Policy citation: {citation}

Tell them what is being asked for, who has already signed off, and precisely why it is now on
their desk. Plain prose, no bullet points, no greeting, no sign-off."""

    try:
        text = _generate(prompt).strip()
        return text or llm_mock.generate_approval_brief(
            label, structured_fields, completed_approvals, reason, source_doc, source_section
        )
    except Exception:
        logger.exception("generate_approval_brief failed; falling back")
        return (
            f"This request requires your approval as {label}. {reason} "
            f"See {citation}."
        )


# -------------------------------------------------------------------- 5. diff

def detect_policy_diff(old_chunks: list[str], new_chunks: list[str]) -> dict:
    if not _live():
        return llm_mock.detect_policy_diff(old_chunks, new_chunks)

    prompt = f"""Compare two versions of an institutional policy and report only the changes that
affect approval workflows — thresholds, required approvers, conditions, limits. Ignore
formatting, numbering and wording changes that do not change a rule.

OLD VERSION:
{chr(10).join(old_chunks[:20])}

NEW VERSION:
{chr(10).join(new_chunks[:20])}

Return ONLY this JSON, no markdown fences:
{{
  "changed": [{{"description": "", "old_text": "", "new_text": "", "impact": ""}}],
  "added":   [{{"description": "", "text": "", "impact": ""}}],
  "removed": [{{"description": "", "text": "", "impact": ""}}]
}}

"impact" must say what happens to workflows — e.g. "procurement requests above Rs 50,000 gain a
Registrar approval node"."""

    try:
        data = parse_json(_generate(prompt))
        return {
            "changed": data.get("changed") or [],
            "added": data.get("added") or [],
            "removed": data.get("removed") or [],
        }
    except Exception:
        logger.exception("detect_policy_diff failed; falling back")
        return llm_mock.detect_policy_diff(old_chunks, new_chunks)
