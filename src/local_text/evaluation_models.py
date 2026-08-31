"""SQLAlchemy models for the separately stored cleanup evaluation corpus."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class EvaluationBase(DeclarativeBase):
    pass


class EvaluationCase(EvaluationBase):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        CheckConstraint(
            "contract_version = 'cleanup-evaluation-corpus-v1'",
            name="ck_evaluation_cases_contract",
        ),
        CheckConstraint(
            "purpose = 'polished-cleanup-evaluation-only'",
            name="ck_evaluation_cases_purpose",
        ),
        CheckConstraint(
            "source_category IN ('dictation', 'typed', 'pasted', 'unknown')",
            name="ck_evaluation_cases_source_category",
        ),
        CheckConstraint("revision >= 1", name="ck_evaluation_cases_revision"),
        CheckConstraint(
            "length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_source_hash",
        ),
        CheckConstraint(
            "length(provider_output_sha256) = 64 "
            "AND provider_output_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_provider_output_hash",
        ),
        CheckConstraint(
            "length(expected_cleanup_sha256) = 64 "
            "AND expected_cleanup_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_expected_cleanup_hash",
        ),
        CheckConstraint(
            "length(prompt_content_sha256) = 64 "
            "AND prompt_content_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_prompt_hash",
        ),
        CheckConstraint(
            "expires_at <= original_expires_at",
            name="ck_evaluation_cases_shortened_expiry",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    source_category: Mapped[str] = mapped_column(String(16), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider_output: Mapped[str] = mapped_column(Text, nullable=False)
    expected_cleanup: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_cleanup_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleanup_schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cleanup_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    consent: Mapped[EvaluationConsent] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    attempts: Mapped[list[EvaluationAttempt]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="EvaluationAttempt.route_index",
    )
    annotations: Mapped[list[EvaluationAnnotation]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="EvaluationAnnotation.id"
    )
    hold: Mapped[BenchmarkHold | None] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )


class EvaluationConsent(EvaluationBase):
    __tablename__ = "evaluation_consents"
    __table_args__ = (
        CheckConstraint(
            "version = 'cleanup-evaluation-consent-v1'",
            name="ck_evaluation_consents_version",
        ),
        CheckConstraint(
            "scope = 'polished-cleanup-evaluation-only'",
            name="ck_evaluation_consents_scope",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case: Mapped[EvaluationCase] = relationship(back_populates="consent")


class EvaluationAttempt(EvaluationBase):
    __tablename__ = "evaluation_attempts"
    __table_args__ = (
        CheckConstraint("route_index >= 0", name="ck_evaluation_attempts_route_index"),
        CheckConstraint("outcome IN ('success', 'failure')", name="ck_evaluation_attempts_outcome"),
        CheckConstraint("elapsed_ms >= 0", name="ck_evaluation_attempts_elapsed"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_evaluation_attempts_input_tokens",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_evaluation_attempts_output_tokens",
        ),
        CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds >= 0",
            name="ck_evaluation_attempts_retry_after",
        ),
        CheckConstraint(
            "cost_usd_micros IS NULL OR cost_usd_micros >= 0",
            name="ck_evaluation_attempts_cost",
        ),
        CheckConstraint(
            "(cost_usd_micros IS NULL AND pricing_snapshot_id IS NULL) OR "
            "(cost_usd_micros IS NOT NULL AND pricing_snapshot_id IS NOT NULL)",
            name="ck_evaluation_attempts_cost_snapshot",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"), primary_key=True
    )
    route_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_class: Mapped[str | None] = mapped_column(String(64))
    provider_code: Mapped[str | None] = mapped_column(String(128))
    http_status: Mapped[int | None] = mapped_column(Integer)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd_micros: Mapped[int | None] = mapped_column(Integer)
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(128))

    case: Mapped[EvaluationCase] = relationship(back_populates="attempts")


class EvaluationAnnotation(EvaluationBase):
    __tablename__ = "evaluation_annotations"
    __table_args__ = (
        CheckConstraint("source_start >= 0", name="ck_evaluation_annotations_source_start"),
        CheckConstraint(
            "source_end >= source_start", name="ck_evaluation_annotations_source_end"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=False
    )
    protocol_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    source_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end: Mapped[int] = mapped_column(Integer, nullable=False)
    acceptable_values_json: Mapped[str] = mapped_column(Text, nullable=False)

    case: Mapped[EvaluationCase] = relationship(back_populates="annotations")


class BenchmarkHold(EvaluationBase):
    __tablename__ = "benchmark_holds"
    __table_args__ = (UniqueConstraint("case_id", name="uq_benchmark_holds_case"),)

    case_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"), primary_key=True
    )
    benchmark_id: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    release_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case: Mapped[EvaluationCase] = relationship(back_populates="hold")
