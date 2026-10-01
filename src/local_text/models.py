"""SQLAlchemy models for durable local configuration."""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    system_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ActivePrompt(Base):
    __tablename__ = "active_prompt"
    __table_args__ = (CheckConstraint("id = 1", name="ck_active_prompt_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    prompt_version_id: Mapped[int] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SeedRelease(Base):
    __tablename__ = "seed_releases"

    release_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    prompt_version_id: Mapped[int] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (CheckConstraint("id = 1", name="ck_import_runs_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    application_name: Mapped[str] = mapped_column(String(80), nullable=False)
    application_bundle_id: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str] = mapped_column(String(16), nullable=False)
    send_strategy: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class TargetOperationError(Base):
    __tablename__ = "target_operation_errors"

    target_id: Mapped[str] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(30), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    retry_action: Mapped[str] = mapped_column(String(300), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PersonalCorrectionProfile(Base):
    __tablename__ = "personal_correction_profiles"
    __table_args__ = (
        CheckConstraint("owner_id = 'local'", name="ck_pc_profiles_local_owner"),
        CheckConstraint("enabled IN (0, 1)", name="ck_pc_profiles_enabled"),
    )

    owner_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _reject_control_characters(column: str) -> str:
    return (
        f"instr({column}, char(0)) = 0 AND "
        f"{column} NOT GLOB ('*[' || char(1) || '-' || char(31) || "
        "char(127) || '-' || char(159) || ']*')"
    )


class PersonalCorrectionEntry(Base):
    __tablename__ = "personal_correction_entries"
    __table_args__ = (
        CheckConstraint(
            "length(intended_term) BETWEEN 1 AND 200",
            name="ck_pc_entries_intended_term_length",
        ),
        CheckConstraint(
            _reject_control_characters("intended_term"),
            name="ck_pc_entries_intended_term_controls",
        ),
        CheckConstraint(
            _reject_control_characters("intended_key"),
            name="ck_pc_entries_intended_key_controls",
        ),
        CheckConstraint(
            "applicability_context IS NULL OR "
            "(length(applicability_context) BETWEEN 1 AND 500 "
            f"AND {_reject_control_characters('applicability_context')})",
            name="ck_pc_entries_context",
        ),
        CheckConstraint("enabled IN (0, 1)", name="ck_pc_entries_enabled"),
        CheckConstraint("revision > 0", name="ck_pc_entries_revision"),
        UniqueConstraint("owner_id", "intended_key", name="uq_pc_entries_owner_key"),
        UniqueConstraint("id", "owner_id", name="uq_pc_entries_id_owner"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("personal_correction_profiles.owner_id", ondelete="CASCADE"), nullable=False
    )
    intended_term: Mapped[str] = mapped_column(Text, nullable=False)
    intended_key: Mapped[str] = mapped_column(Text, nullable=False)
    applicability_context: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PersonalCorrectionAlias(Base):
    __tablename__ = "personal_correction_aliases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_id", "owner_id"],
            ["personal_correction_entries.id", "personal_correction_entries.owner_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(observed_alias) BETWEEN 1 AND 200",
            name="ck_pc_aliases_observed_alias_length",
        ),
        CheckConstraint(
            _reject_control_characters("observed_alias"),
            name="ck_pc_aliases_observed_alias_controls",
        ),
        CheckConstraint(
            _reject_control_characters("alias_key"),
            name="ck_pc_aliases_alias_key_controls",
        ),
        UniqueConstraint(
            "owner_id", "entry_id", "alias_key", name="uq_pc_aliases_owner_entry_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    observed_alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
