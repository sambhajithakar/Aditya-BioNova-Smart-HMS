"""Request/response schemas for phase AI-1 (forecasts, knowledge, agents,
scribe, governance). Inputs are strict (extra keys rejected); outputs that
carry engine results allow extra keys but always validate the governance
fields (status / label / inference)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import StrictModel


# --- forecasts ---------------------------------------------------------------------------
class ForecastOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["ok", "insufficient_data"]
    kind: str
    label: Literal["statistical model"]
    inference: Literal["statistical"]


class ModelRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    scope: str
    engine_version: str
    method: str
    status: str
    params: dict
    metrics: dict
    baseline_metrics: dict
    data_start: date | None
    data_end: date | None
    n_obs: int
    trained_at: datetime


# --- knowledge ---------------------------------------------------------------------------
class KbDocumentIn(StrictModel):
    title: str = Field(min_length=2, max_length=200)
    doc_type: Literal["sop", "manual", "policy", "training", "other"] = "sop"
    language: Literal["en", "mr", "hi", "mixed"] | None = None
    text: str = Field(min_length=20, max_length=200000)
    visibility_roles: list[str] = Field(default_factory=list, max_length=20)
    contains_patient_data: bool
    file_name: str | None = Field(default=None, max_length=200)


class KbDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    doc_type: str
    language: str
    version: int
    status: str
    visibility_roles: list[str]
    injection_flags: int
    chunk_count: int
    uploaded_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime


class KbDocumentDetailOut(KbDocumentOut):
    body: str


class KbAskIn(StrictModel):
    question: str = Field(min_length=2, max_length=500)
    language: Literal["en", "mr", "hi"] | None = None


class KbCitation(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    section: str
    version: int
    score: float


class KbSentence(BaseModel):
    text: str
    citation: KbCitation


class KbAnswerOut(BaseModel):
    request_id: uuid.UUID | None
    answered: bool
    language: str
    answer: list[KbSentence]
    refusal: str | None
    retrieved: list[KbCitation]
    inference: str
    provider: str
    model: str
    method: str
    grounded: bool
    note: str | None = None


class RagModelOutput(BaseModel):
    """Schema EVERY provider's RAG output must satisfy."""
    model_config = ConfigDict(extra="forbid")

    class Sent(BaseModel):
        model_config = ConfigDict(extra="forbid")
        text: str = Field(min_length=1, max_length=1500)
        chunk_id: str

    sentences: list[Sent] = Field(max_length=6)
    refused: bool


# --- agents ------------------------------------------------------------------------------
class AgentRunIn(StrictModel):
    agent: Literal["appointment_followups", "inventory_monitor", "billing_reconciliation",
                   "ops_daily_report"]
    branch_id: uuid.UUID | None = None
    older_than_days: int = Field(default=7, ge=0, le=365)


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: str
    kind: str
    status: str
    branch_id: uuid.UUID | None
    title: str
    payload: dict
    rationale: str
    evidence: list
    args_sha256: str
    created_by: uuid.UUID | None
    created_at: datetime
    expires_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str
    executed_at: datetime | None
    result: dict | None
    approve_requires: list[str] = []
    executable: bool = False


class ProposalEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor_user_id: uuid.UUID | None
    note: str
    created_at: datetime


class ProposalDecisionIn(StrictModel):
    note: str = Field(default="", max_length=500)


class AgentRunOut(BaseModel):
    agent: str
    created: list[ProposalOut]
    skipped_duplicates: int
    inference: Literal["deterministic"] = "deterministic"
    note: str


class StaffTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    kind: str
    title: str
    subject_type: str | None
    subject_id: uuid.UUID | None
    due_date: date | None
    priority: str
    status: str
    created_at: datetime


class ReorderDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID
    proposal_id: uuid.UUID | None
    lines: list
    status: str
    created_at: datetime


# --- scribe ------------------------------------------------------------------------------
class ScribeConsentIn(StrictModel):
    patient_verbal_consent: bool
    notice_language: Literal["en", "mr", "hi"] = "en"


class ScribeSessionIn(StrictModel):
    encounter_id: uuid.UUID
    consent: ScribeConsentIn


class AudioMetaIn(StrictModel):
    duration_s: float = Field(gt=0, le=7200)
    mime: str = Field(max_length=60)


class ScribeTranscriptIn(StrictModel):
    transcript: str | None = Field(default=None, max_length=30000)
    audio: AudioMetaIn | None = None


class ScribeAcceptIn(StrictModel):
    chief_complaint: str = Field(default="", max_length=500)
    history: str = Field(default="", max_length=5000)
    examination: str = Field(default="", max_length=5000)
    assessment: str = Field(default="", max_length=5000)
    plan: str = Field(default="", max_length=5000)
    reviewed: bool


class ScribeSessionOut(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    clinician_id: uuid.UUID
    consent_id: uuid.UUID
    consent_given_at: datetime
    consent_obtained_by: uuid.UUID
    status: str
    transcriber: str
    transcriber_label: str
    segments: list[dict] = []
    draft: dict | None = None
    draft_valid: bool | None = None
    validation_problems: list[str] = []
    prefill: dict | None = None
    inference: str
    provider: str
    model: str
    audio_stored: bool
    audio_retention: str
    accepted_by: uuid.UUID | None = None
    accepted_at: datetime | None = None
    accepted_fields: list[str] = []
    disclaimer: str


# --- governance --------------------------------------------------------------------------
class UsageBreakdownRow(BaseModel):
    feature: str
    task: str
    inference: str
    requests: int
    ok: int
    credits: int


class UsageBreakdownOut(BaseModel):
    period: str
    used_credits: int
    limit_credits: int | None
    rows: list[UsageBreakdownRow]
    features: dict
