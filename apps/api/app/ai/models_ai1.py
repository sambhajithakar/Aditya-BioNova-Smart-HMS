"""ORM models for phase AI-1 (migration 0016). Tenant-scoped, strict RLS."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Identity, Integer, \
    Numeric, String, Text, text
from sqlalchemy import Index, UniqueConstraint  # noqa: E402  (table args)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                         nullable=False)


def _user() -> Mapped[uuid.UUID | None]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AiModelRun(Base):
    __tablename__ = "ai_model_runs"
    __table_args__ = (
        Index("ix_modelrun_org_kind", "organization_id", "kind", "trained_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False, default="all")
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    baseline_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    n_obs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trained_by: Mapped[uuid.UUID | None] = _user()
    trained_at: Mapped[datetime] = _created()


class KbDocument(Base):
    __tablename__ = "kb_documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "title", "version", name="uq_kbdoc_title_ver"),
        Index("ix_kbdoc_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    visibility_roles: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False,
                                                        default=list)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    injection_flags: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _created()
    approved_by: Mapped[uuid.UUID | None] = _user()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = _created()


class KbChunk(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_kbchunk_doc_ord"),
        Index("ix_kbchunk_org_doc", "organization_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_documents.id", ondelete="RESTRICT"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_at: Mapped[datetime] = _created()


class AiProposal(Base):
    __tablename__ = "ai_proposals"
    __table_args__ = (
        Index("ix_proposal_org_status", "organization_id", "status", "created_at"),
        Index("uq_proposal_open_dedupe", "organization_id", "dedupe_key", unique=True,
              postgresql_where=text("status = 'proposed'")),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    agent: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    args_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = _user()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class AiProposalEvent(Base):
    __tablename__ = "ai_proposal_events"
    __table_args__ = (
        Index("ix_propevent_org_prop", "organization_id", "proposal_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[uuid.UUID] = _org()
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_proposals.id", ondelete="RESTRICT"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = _user()
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = _created()


class AiStaffTask(Base):
    __tablename__ = "ai_staff_tasks"
    __table_args__ = (
        Index("ix_stafftask_org_status", "organization_id", "status", "due_date"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_proposals.id", ondelete="RESTRICT"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _created()
    completed_by: Mapped[uuid.UUID | None] = _user()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiReorderDraft(Base):
    __tablename__ = "ai_reorder_drafts"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_proposals.id", ondelete="RESTRICT"), nullable=True)
    lines: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _created()


class ScribeConsent(Base):
    __tablename__ = "scribe_consents"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False)
    obtained_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    notice_language: Mapped[str] = mapped_column(String(5), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(20), nullable=False)
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                               server_default=text("now()"))


class ScribeSession(Base):
    __tablename__ = "scribe_sessions"
    __table_args__ = (
        Index("ix_scribesession_org_enc", "organization_id", "encounter_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org()
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    clinician_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scribe_consents.id", ondelete="RESTRICT"),
        nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="consented")
    transcriber: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    transcript_sealed: Mapped[str | None] = mapped_column(Text, nullable=True)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draft_sealed: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True)
    audio_stored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepted_by: Mapped[uuid.UUID | None] = _user()
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_fields: Mapped[list[str]] = mapped_column(ARRAY(String(30)), nullable=False,
                                                       default=list)
    edit_ratio: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()
