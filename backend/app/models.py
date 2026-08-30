from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    file_path: Mapped[str] = mapped_column(String(500), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    chunks: Mapped[list["PolicyChunk"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id", ondelete="CASCADE"), index=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    #: 768-float Gemini embedding, stored as JSON so the same schema runs on SQLite and Postgres.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    source_section: Mapped[str | None] = mapped_column(String(50), nullable=True)

    policy: Mapped[Policy] = relationship(back_populates="chunks")


class ApproverContact(Base):
    __tablename__ = "approver_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_text: Mapped[str] = mapped_column(Text)
    structured_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    conversation: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    submitted_by: Mapped[str] = mapped_column(String(200), index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    nodes: Mapped[list["WorkflowNode"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="blocked", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    source_doc: Mapped[str] = mapped_column(String(200), default="")
    source_section: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parallel_group: Mapped[str | None] = mapped_column(String(80), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=1)
    approval_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The generated brief last sent to this node's approver — shown to the student (read-only,
    #: content only) so the transparency the DAG already gives extends to the email itself.
    email_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    request: Mapped[Request] = relationship(back_populates="nodes")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
