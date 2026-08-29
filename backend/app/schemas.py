from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RequestCreate(BaseModel):
    text: str


class AnswerIn(BaseModel):
    field: str
    value: str


class RejectionIn(BaseModel):
    reason: str


class ContactIn(BaseModel):
    role: str
    label: str
    email: str


class ContactOut(ContactIn):
    id: int


class SubmitResponse(BaseModel):
    request_id: int
    status: str
    question: str | None = None
    asking_for: str | None = None
    fields_extracted: dict | None = None
    workflow_compiled: bool | None = None
    immediate_blocks: list[str] | None = None


class NodeOut(BaseModel):
    id: int
    role: str
    label: str
    status: str
    reason: str
    source_doc: str
    source_section: str | None
    parallel_group: str | None
    order_index: int
    activated_at: datetime | None
    completed_at: datetime | None


class WorkflowOut(BaseModel):
    request_id: int
    status: str
    structured_fields: dict
    conversation: list
    nodes: list[NodeOut]


class RequestSummaryOut(BaseModel):
    id: int
    purpose: str
    status: str
    created_at: datetime


class PolicyOut(BaseModel):
    id: int
    name: str
    uploaded_at: datetime
    is_active: bool
    version: int
