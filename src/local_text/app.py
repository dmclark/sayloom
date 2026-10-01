"""FastAPI application entry point."""

import re
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from local_text.cleanup import (
    GEMINI_37_FLASH,
    OPENAI_GPT_56_LUNA,
    CleanupPartitionSchedule,
    CleanupRequest,
    CleanupResult,
    CleanupRoute,
    CleanupService,
    CorrectionMode,
    GeminiAdapter,
    OpenAIAdapter,
    PreparationMode,
    SequentialCleanupProvider,
)
from local_text.config import Profile, Settings, load_settings
from local_text.database import ApplicationDatabase
from local_text.evidence_collection import EvidenceCollection, EvidenceCollectionError
from local_text.personal_corrections import (
    PersonalCorrectionConflictError,
    PersonalCorrectionError,
    PersonalCorrectionNotFoundError,
    PersonalCorrectionRevisionConflictError,
    PersonalCorrectionStore,
)
from local_text.prompt_store import PromptNotFoundError, PromptRecord, PromptStore, SeedStateError
from local_text.state import OutgoingStateStore, OutgoingStateUpdate
from local_text.target_adapter import TargetAdapter, TargetArtifactError
from local_text.target_store import TargetNotFoundError, TargetRecord, TargetStore
from local_text.targets import TargetDefinition, generate_command

STATIC_DIRECTORY = Path(__file__).parent / "static"
INDEX_TEMPLATE = (STATIC_DIRECTORY / "index.html").read_text()
STATIC_VERSION = sha256(
    b"".join((STATIC_DIRECTORY / filename).read_bytes() for filename in ("app.css", "app.js"))
).hexdigest()[:12]
PAID_DATA_ACKNOWLEDGEMENT = "paid-external-cleanup-v1"
CROSS_PROVIDER_ROUTE_ORDER = "gemini,openai"
SAFE_CONFIGURATION_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


@dataclass(frozen=True)
class CleanupRuntimeConfiguration:
    status: str
    routes: tuple[tuple[str, str, str], ...] = ()
    partition_schedule: CleanupPartitionSchedule | None = None
    validation_error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.routes)

    def public(self) -> dict[str, object]:
        if self.status == "cross_provider":
            disclosure = {
                "summary": "Paid Gemini → OpenAI fallback",
                "processing": (
                    "Cleanup sends the current text and cleanup instruction to paid Gemini "
                    "for external processing."
                ),
                "fallback": (
                    "Only after a qualifying Gemini failure, the same current text and cleanup "
                    "instruction may be sent to paid OpenAI."
                ),
                "corpus": (
                    "Routine cleanup does not retain Original, Prepared, or provider payloads."
                ),
            }
        elif self.status == "gemini_only":
            disclosure = {
                "summary": "Gemini-only cleanup",
                "processing": (
                    "Cleanup sends the current text and cleanup instruction to Gemini for "
                    "external processing."
                ),
                "fallback": "Fallback stays within the configured Gemini route.",
                "corpus": (
                    "Routine cleanup does not retain Original, Prepared, or provider payloads."
                ),
            }
        elif self.status == "invalid":
            disclosure = {
                "summary": "Cleanup configuration is invalid",
                "processing": "No cleanup provider client is active.",
                "fallback": "Cleanup remains available as Original fail-open only.",
                "corpus": (
                    "Routine cleanup does not retain Original, Prepared, or provider payloads."
                ),
            }
        else:
            disclosure = {
                "summary": "Cleanup provider is not configured",
                "processing": "No cleanup provider client is active.",
                "fallback": "Cleanup remains available as Original fail-open only.",
                "corpus": (
                    "Routine cleanup does not retain Original, Prepared, or provider payloads."
                ),
            }
        return {
            "status": self.status,
            "available": self.available,
            "routes": [
                {"provider": provider, "model": model}
                for provider, model, _quota_group in self.routes
            ],
            "fallback_enabled": len(self.routes) > 1,
            "paid_data_acknowledgement": (
                PAID_DATA_ACKNOWLEDGEMENT if self.status == "cross_provider" else None
            ),
            "validation_error": self.validation_error,
            "disclosure": disclosure,
        }


def _cleanup_runtime_configuration(runtime: Settings) -> CleanupRuntimeConfiguration:
    cross_provider_requested = any(
        value is not None
        for value in (
            runtime.openai_api_key,
            runtime.openai_model,
            runtime.cleanup_route_order,
            runtime.gemini_quota_group_id,
            runtime.openai_quota_group_id,
            runtime.paid_data_acknowledgement,
        )
    )
    if not cross_provider_requested:
        if not runtime.gemini_api_key:
            return CleanupRuntimeConfiguration("unavailable")
        return _configured_cleanup_routes(
            runtime,
            "gemini_only",
            (
                ("gemini", runtime.gemini_model, "gemini-default"),
                ("gemini", "gemini-2.5-flash", "gemini-default"),
            ),
        )

    validation_error = _cross_provider_validation_error(runtime)
    if validation_error is not None:
        return CleanupRuntimeConfiguration("invalid", validation_error=validation_error)
    return _configured_cleanup_routes(
        runtime,
        "cross_provider",
        (
            ("gemini", GEMINI_37_FLASH, runtime.gemini_quota_group_id or ""),
            ("openai", OPENAI_GPT_56_LUNA, runtime.openai_quota_group_id or ""),
        ),
    )


def _configured_cleanup_routes(
    runtime: Settings,
    status: str,
    routes: tuple[tuple[str, str, str], ...],
) -> CleanupRuntimeConfiguration:
    allocations = runtime.cleanup_route_attempt_seconds
    if allocations is None:
        return CleanupRuntimeConfiguration(
            "invalid", validation_error="route_attempt_allocations_required"
        )
    try:
        schedule = CleanupPartitionSchedule(runtime.cleanup_timeout_seconds, allocations)
    except ValueError:
        return CleanupRuntimeConfiguration(
            "invalid", validation_error="route_attempt_allocations_invalid"
        )
    if len(allocations) != len(routes):
        return CleanupRuntimeConfiguration(
            "invalid", validation_error="route_attempt_allocation_count_mismatch"
        )
    return CleanupRuntimeConfiguration(status, routes, schedule)


def _cross_provider_validation_error(runtime: Settings) -> str | None:
    if runtime.cleanup_route_order != CROSS_PROVIDER_ROUTE_ORDER:
        return "route_order_must_be_gemini_openai"
    if not runtime.gemini_api_key or not runtime.gemini_api_key_is_explicit:
        return "explicit_gemini_credential_required"
    if runtime.gemini_model != GEMINI_37_FLASH:
        return "gemini_model_must_be_gemini_3_7_flash"
    if not _safe_configuration_identifier(runtime.gemini_quota_group_id):
        return "gemini_quota_group_required"
    if not runtime.openai_api_key:
        return "explicit_openai_credential_required"
    if runtime.openai_model != OPENAI_GPT_56_LUNA:
        return "openai_model_must_be_gpt_5_6_luna"
    if not _safe_configuration_identifier(runtime.openai_quota_group_id):
        return "openai_quota_group_required"
    if runtime.gemini_quota_group_id == runtime.openai_quota_group_id:
        return "provider_quota_groups_must_differ"
    if runtime.paid_data_acknowledgement != PAID_DATA_ACKNOWLEDGEMENT:
        return "paid_data_acknowledgement_required"
    return None


def _safe_configuration_identifier(value: str | None) -> bool:
    return value is not None and SAFE_CONFIGURATION_IDENTIFIER.fullmatch(value) is not None


class PromptCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    system_text: str = Field(min_length=1, max_length=100_000)
    activate: bool = True

    @field_validator("title", "system_text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PreparationDefaultRequest(BaseModel):
    preparation_default: PreparationMode


class PersonalCorrectionProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class PersonalCorrectionEntryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intended_term: str = Field(min_length=1, max_length=200)
    aliases: tuple[Annotated[str, Field(min_length=1, max_length=200)], ...] = Field(
        min_length=1, max_length=50
    )
    applicability_context: str | None = Field(default=None, max_length=500)


class PersonalCorrectionEntryUpdateRequest(PersonalCorrectionEntryCreateRequest):
    expected_revision: int = Field(ge=1)
    enabled: bool


class EvidenceArmRequest(BaseModel):
    browser_session_id: UUID
    source_attestation_confirmed: bool


class EvidenceTriggerRequest(BaseModel):
    lease_token: UUID
    original_text: str = Field(min_length=1, max_length=100_000)
    task_context: str | None = Field(default=None, max_length=4_000)
    curated_knowledge_enabled: bool = False
    relevant_curated_knowledge: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = (
        Field(default=(), max_length=50)
    )
    prompt_version_id: int | None = Field(default=None, ge=1)
    correction_mode: CorrectionMode = CorrectionMode.SMART

    @field_validator("relevant_curated_knowledge")
    @classmethod
    def profile_is_explicitly_enabled(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        if value and not info.data.get("curated_knowledge_enabled", False):
            raise ValueError("curated knowledge must be explicitly enabled")
        return value


class EvidenceConfirmRequest(BaseModel):
    lease_token: UUID
    observation_id: UUID
    disposition: str
    intended_text: str | None = Field(default=None, max_length=100_000)

    @field_validator("intended_text")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class EvidenceCancelRequest(BaseModel):
    lease_token: UUID


def _prompt_response(prompt: PromptRecord, *, active: bool) -> dict[str, object]:
    created_at = prompt.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return {
        **asdict(prompt),
        "created_at": created_at.isoformat(),
        "active": active,
    }


def create_app(
    settings: Settings | None = None,
    cleanup_service: CleanupService | None = None,
    target_adapter: TargetAdapter | None = None,
) -> FastAPI:
    runtime = settings or load_settings()
    database = ApplicationDatabase(runtime.resolved_database_path)
    schema = database.schema_status()
    evidence = EvidenceCollection(runtime.evidence_package_directory)
    prompts = PromptStore(database)
    targets = TargetStore(database)
    personal_corrections = PersonalCorrectionStore(database)
    adapter = target_adapter or TargetAdapter(runtime.resolved_raycast_directory)
    configuration_error: str | None = None
    preparation_default = PreparationMode.CONSERVATIVE
    if schema.ready:
        try:
            preparation_default = prompts.preparation_default()
            prompts.active()
        except SeedStateError as exc:
            configuration_error = str(exc)
    cleanup_enabled = preparation_default is not PreparationMode.OFF
    default_correction_mode = (
        CorrectionMode.SMART
        if preparation_default is PreparationMode.SMART
        else CorrectionMode.CONSERVATIVE
    )
    state = OutgoingStateStore(
        cleanup_enabled=cleanup_enabled,
        correction_mode=default_correction_mode,
    )
    cleanup_configuration = _cleanup_runtime_configuration(runtime)
    disabled_cleanup = CleanupService(
        provider=None,
        model=runtime.gemini_model,
        timeout_seconds=runtime.cleanup_timeout_seconds,
        provider_id="gemini",
    )
    cleanup_available = cleanup_configuration.available or cleanup_service is not None

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if cleanup_service is not None or not cleanup_configuration.available:
            application.state.cleanup_service = cleanup_service or disabled_cleanup
            yield
            return
        clients: dict[str, httpx.AsyncClient] = {}
        try:
            adapters = []
            for provider_id, model, quota_group_id in cleanup_configuration.routes:
                client = clients.get(provider_id)
                if client is None:
                    client = _new_provider_client(runtime.cleanup_timeout_seconds)
                    clients[provider_id] = client
                adapter = (
                    GeminiAdapter(
                        runtime.gemini_api_key or "",
                        model,
                        client,
                        quota_group_id=quota_group_id,
                        traffic_diagnostics_enabled=(
                            runtime.provider_traffic_diagnostics_enabled
                        ),
                    )
                    if provider_id == "gemini"
                    else OpenAIAdapter(
                        runtime.openai_api_key or "",
                        client,
                        model=model,
                        quota_group_id=quota_group_id,
                        traffic_diagnostics_enabled=(
                            runtime.provider_traffic_diagnostics_enabled
                        ),
                    )
                )
                adapters.append(
                    CleanupRoute(
                        adapter=adapter,
                        quota_group_id=quota_group_id,
                    )
                )
            assert cleanup_configuration.partition_schedule is not None
            provider = SequentialCleanupProvider(
                tuple(adapters),
                partition_schedule=cleanup_configuration.partition_schedule,
            )
            application.state.cleanup_service = CleanupService(
                provider=provider,
                model=cleanup_configuration.routes[0][1],
                timeout_seconds=runtime.cleanup_timeout_seconds,
                provider_id="gemini",
            )
            yield
        finally:
            application.state.cleanup_service = disabled_cleanup
            for client in clients.values():
                await client.aclose()

    application = FastAPI(title=runtime.page_title, lifespan=lifespan)
    application.state.cleanup_service = cleanup_service or disabled_cleanup
    application.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")

    @application.exception_handler(RequestValidationError)
    async def privacy_safe_validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        if request.url.path.startswith("/api/personal-corrections"):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": {
                        "code": "invalid_personal_correction_request",
                        "message": "The request did not match the Personal corrections contract.",
                        "retry_action": "Review the current form values and retry.",
                    }
                },
            )
        if request.url.path.startswith("/api/evidence-collection/"):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": {
                        "code": "invalid_evidence_collection_request",
                        "message": "The request did not match the evidence collection contract.",
                        "retry_action": "Review the current form values and retry.",
                    }
                },
            )
        return await request_validation_exception_handler(request, exc)

    @application.get("/health")
    def health(response: Response) -> dict[str, object]:
        ready = schema.ready and configuration_error is None
        if not ready:
            response.status_code = 503
        return {
            "status": "ok" if ready else "setup_required",
            "profile": runtime.profile,
            "development_state": runtime.development_state_name,
            "database": {
                "state": schema.state,
                "current_revision": schema.current_revision,
                "expected_revision": schema.expected_revision,
            },
            "configuration_error": configuration_error,
            "cleanup_configuration": cleanup_configuration.public(),
            "evidence_collection": evidence.readiness(),
        }

    def require_configuration() -> None:
        if not schema.ready:
            raise HTTPException(
                status_code=503,
                detail=f"database schema is {schema.state}; run the controlled update workflow",
            )
        if configuration_error is not None:
            raise HTTPException(status_code=503, detail=configuration_error)

    @application.get("/", response_class=HTMLResponse)
    def development_page() -> str:
        development_badge = ""
        if runtime.profile is Profile.DEVELOPMENT:
            badge_text = "DEV"
            badge_label = "Development profile"
            if runtime.development_state_name:
                state_name = escape(runtime.development_state_name)
                badge_text = f"DEV · {state_name}"
                badge_label = f"Development state {state_name}"
            development_badge = (
                f'<span class="development-badge" aria-label="{badge_label}">{badge_text}</span>'
            )
        return (
            INDEX_TEMPLATE.replace("__PAGE_TITLE__", escape(runtime.page_title))
            .replace("__DISPLAY_NAME__", escape(runtime.display_name))
            .replace("__PROFILE__", escape(runtime.profile.value))
            .replace("__DEVELOPMENT_BADGE__", development_badge)
            .replace("__STATIC_VERSION__", STATIC_VERSION)
        )

    @application.get("/api/config")
    def browser_config(request: Request) -> dict[str, object]:
        require_configuration()
        browser_session_id = request.headers.get("X-Evidence-Browser-Session")
        if browser_session_id is not None:
            try:
                previous_lease = request.headers.get("X-Evidence-Previous-Lease")
                evidence.begin_browser_session(
                    UUID(browser_session_id),
                    previous_lease_token=UUID(previous_lease) if previous_lease else None,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="invalid browser session or prior lease",
                ) from exc
        return {
            "display_name": runtime.display_name,
            "profile": runtime.profile,
            "development_state": runtime.development_state_name,
            "preparation_default": prompts.preparation_default(),
            "cleanup_available": cleanup_available,
            "cleanup_model": cleanup_configuration.routes[0][1]
            if cleanup_configuration.routes
            else runtime.gemini_model,
            "cleanup_configuration": cleanup_configuration.public(),
            "evidence_collection": evidence.readiness(),
        }

    def evidence_failure(exc: EvidenceCollectionError) -> None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "evidence_collection_unavailable",
                "message": str(exc),
                "retry_action": "Stop collection, verify readiness, then attest and arm again.",
            },
        ) from None

    @application.post("/api/evidence-collection/arm")
    def arm_evidence_collection(request: EvidenceArmRequest) -> dict[str, object]:
        require_configuration()
        try:
            lease = evidence.arm(
                browser_session_id=request.browser_session_id,
                attested=request.source_attestation_confirmed,
            )
        except EvidenceCollectionError as exc:
            evidence_failure(exc)
        return {
            "lease_token": lease.token,
            "expires_at": lease.expires_at.isoformat().replace("+00:00", "Z"),
            "source_attestation_version": lease.source_attestation_version,
            "package_version": lease.package_version,
            "package_contract_version": lease.package_contract_version,
        }

    @application.delete("/api/evidence-collection/arm", status_code=status.HTTP_204_NO_CONTENT)
    def disarm_evidence_collection(lease_token: UUID) -> Response:
        try:
            evidence.stop(lease_token=lease_token)
        except EvidenceCollectionError as exc:
            evidence_failure(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.post("/api/evidence-collection/cancel", status_code=status.HTTP_204_NO_CONTENT)
    def cancel_evidence_collection(request: EvidenceCancelRequest) -> Response:
        try:
            evidence.cancel(lease_token=request.lease_token)
        except EvidenceCollectionError as exc:
            evidence_failure(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.post("/api/evidence-collection/trigger")
    def trigger_evidence_collection(request: EvidenceTriggerRequest) -> dict[str, object]:
        require_configuration()
        try:
            prompt = (
                prompts.get(request.prompt_version_id)
                if request.prompt_version_id is not None
                else prompts.active()
            )
            observation = evidence.trigger(
                lease_token=request.lease_token,
                original=request.original_text,
                task_context=request.task_context,
                profile_enabled=request.curated_knowledge_enabled,
                relevant_profile_evidence=request.relevant_curated_knowledge,
                prompt_version_id=prompt.id,
                prompt_content_sha256=prompt.content_sha256,
                correction_mode=request.correction_mode,
            )
        except PromptNotFoundError as exc:
            evidence.disarm()
            raise HTTPException(
                status_code=409, detail="the selected prompt is unavailable"
            ) from exc
        except EvidenceCollectionError as exc:
            evidence_failure(exc)
        return {"observation_id": observation.observation_id}

    @application.post("/api/evidence-collection/confirm")
    async def confirm_evidence_collection(request: EvidenceConfirmRequest) -> dict[str, object]:
        require_configuration()
        try:
            confirmation = evidence.confirm(
                lease_token=request.lease_token,
                observation_id=request.observation_id,
                disposition=request.disposition,
                intended=request.intended_text,
            )
        except EvidenceCollectionError as exc:
            evidence_failure(exc)
        observation = confirmation.observation
        prompt = prompts.get(observation.prompt_version_id)
        cleanup_request = CleanupRequest(
            original_text=observation.original,
            enabled=True,
            correction_mode=CorrectionMode(observation.correction_mode),
            prompt_version_id=observation.prompt_version_id,
            task_context=observation.task_context,
            curated_knowledge_enabled=observation.profile_enabled,
            relevant_curated_knowledge=observation.relevant_profile_evidence,
        )
        result = await application.state.cleanup_service.clean(cleanup_request, prompt.system_text)
        return {
            **result.model_dump(mode="json"),
            "evidence_receipt": str(confirmation.receipt.token),
            "observation_id": str(observation.observation_id),
            "artifact_type": confirmation.receipt.artifact_type,
            "exact_repeat_suggestions": [
                str(item) for item in confirmation.exact_repeat_suggestions
            ],
        }

    @application.delete(
        "/api/evidence-collection/observations/{observation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def withdraw_evidence_observation(observation_id: UUID) -> Response:
        try:
            evidence.withdraw(observation_id=observation_id)
        except EvidenceCollectionError as exc:
            evidence_failure(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.put("/api/preferences/preparation-default")
    def update_preparation_default(
        request: PreparationDefaultRequest,
    ) -> dict[str, PreparationMode]:
        require_configuration()
        prompts.set_preparation_default(request.preparation_default)
        return {"preparation_default": request.preparation_default}

    def personal_correction_response(record) -> dict[str, object]:
        return asdict(record)

    def personal_correction_failure(exc: PersonalCorrectionError) -> None:
        if isinstance(exc, PersonalCorrectionNotFoundError):
            raise HTTPException(status_code=404, detail="Personal correction does not exist")
        if isinstance(exc, PersonalCorrectionRevisionConflictError):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "stale_personal_correction_revision",
                    "message": "This Personal correction changed since it was opened.",
                    "retry_action": "Reload Personal corrections and apply the edit again.",
                },
            )
        if isinstance(exc, PersonalCorrectionConflictError):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "personal_correction_conflict",
                    "message": "A conflicting Personal correction already exists.",
                    "retry_action": "Reload Personal corrections and edit the existing entry.",
                },
            )
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_personal_correction",
                "message": "The Personal correction contains an invalid value.",
                "retry_action": "Review the current form values and retry.",
            },
        )

    @application.get("/api/personal-corrections")
    def get_personal_corrections(response: Response) -> dict[str, object]:
        require_configuration()
        response.headers["Cache-Control"] = "no-store"
        return personal_correction_response(personal_corrections.read())

    @application.put("/api/personal-corrections/profile")
    def update_personal_correction_profile(
        request: PersonalCorrectionProfileRequest, response: Response
    ) -> dict[str, object]:
        require_configuration()
        response.headers["Cache-Control"] = "no-store"
        return personal_correction_response(
            personal_corrections.set_profile_enabled(request.enabled)
        )

    @application.post(
        "/api/personal-corrections/entries", status_code=status.HTTP_201_CREATED
    )
    def create_personal_correction(
        request: PersonalCorrectionEntryCreateRequest, response: Response
    ) -> dict[str, object]:
        require_configuration()
        response.headers["Cache-Control"] = "no-store"
        try:
            record = personal_corrections.create_entry(
                intended_term=request.intended_term,
                aliases=request.aliases,
                applicability_context=request.applicability_context,
            )
        except PersonalCorrectionError as exc:
            personal_correction_failure(exc)
        return personal_correction_response(record)

    @application.put("/api/personal-corrections/entries/{entry_id}")
    def update_personal_correction(
        entry_id: str,
        request: PersonalCorrectionEntryUpdateRequest,
        response: Response,
    ) -> dict[str, object]:
        require_configuration()
        response.headers["Cache-Control"] = "no-store"
        try:
            record = personal_corrections.update_entry(
                entry_id,
                expected_revision=request.expected_revision,
                intended_term=request.intended_term,
                aliases=request.aliases,
                applicability_context=request.applicability_context,
                enabled=request.enabled,
            )
        except PersonalCorrectionError as exc:
            personal_correction_failure(exc)
        return personal_correction_response(record)

    @application.post("/api/cleanup", response_model=CleanupResult)
    async def clean_text(request: CleanupRequest) -> CleanupResult:
        require_configuration()
        try:
            prompt = (
                prompts.get(request.prompt_version_id)
                if request.prompt_version_id is not None
                else prompts.active()
            )
        except PromptNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "prompt_version_not_found",
                    "message": "The selected prompt version is no longer available.",
                    "retry_action": "Reload prompt versions and retry cleanup.",
                },
            ) from exc
        result = await application.state.cleanup_service.clean(request, prompt.system_text)
        return result

    @application.get("/api/prompts")
    def prompt_history() -> dict[str, object]:
        require_configuration()
        history, selected_id = prompts.history()
        return {
            "active_prompt_version_id": selected_id,
            "versions": [
                _prompt_response(prompt, active=prompt.id == selected_id) for prompt in history
            ],
        }

    @application.post("/api/prompts", status_code=201)
    def create_prompt(request: PromptCreateRequest) -> dict[str, object]:
        require_configuration()
        prompt = prompts.create(
            title=request.title,
            system_text=request.system_text,
            activate=request.activate,
        )
        return _prompt_response(prompt, active=request.activate)

    @application.post("/api/prompts/{prompt_version_id}/activate")
    def activate_prompt(prompt_version_id: int) -> dict[str, object]:
        require_configuration()
        try:
            prompt = prompts.activate(prompt_version_id)
        except PromptNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _prompt_response(prompt, active=True)

    @application.get("/api/outgoing-state")
    def outgoing_state() -> dict[str, object]:
        require_configuration()
        published = state.read()
        if not evidence.outgoing_allowed(
            original=published.original_text,
            lease_token=published.evidence_lease_token,
            receipt_token=published.evidence_receipt,
        ):
            raise HTTPException(
                status_code=409,
                detail="Complete intended-meaning confirmation in Sayloom, then retry.",
            )
        return published.public()

    @application.put("/api/outgoing-state")
    def publish_outgoing_state(update: OutgoingStateUpdate) -> dict[str, object]:
        require_configuration()
        return state.update(update).public()

    @application.delete("/api/outgoing-state")
    def clear_outgoing_state() -> dict[str, object]:
        require_configuration()
        saved_default = prompts.preparation_default()
        return state.clear(
            cleanup_enabled=saved_default is not PreparationMode.OFF,
            correction_mode=(
                CorrectionMode.SMART
                if saved_default is PreparationMode.SMART
                else CorrectionMode.CONSERVATIVE
            ),
        ).public()

    def target_or_404(target_id: str) -> TargetRecord:
        try:
            return targets.get(target_id)
        except TargetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="target does not exist") from exc

    def target_response(target: TargetRecord) -> dict[str, object]:
        generated = generate_command(target.id, target.definition)
        observation = adapter.observe(target.id, generated)
        primary_state = "disabled" if not target.enabled else observation.installation.value
        return {
            "id": target.id,
            "display_name": target.display_name,
            "application_name": target.application_name,
            "application_bundle_id": target.application_bundle_id,
            "icon": target.icon,
            "send_strategy": target.send_strategy,
            "enabled": target.enabled,
            "created_at": target.created_at.isoformat(),
            "updated_at": target.updated_at.isoformat(),
            "preview": generated.content,
            "preview_sha256": generated.sha256,
            "state": primary_state,
            "installation": observation.installation,
            "availability": observation.availability,
            "availability_action": observation.availability_action,
            "permission": observation.permission,
            "permission_action": observation.permission_action,
            "errors": [asdict(error) for error in targets.errors(target.id)],
        }

    def artifact_failure(target_id: str, operation: str, exc: TargetArtifactError) -> None:
        targets.record_error(target_id, operation, exc.code, exc.message, exc.retry_action)
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": exc.message,
                "retry_action": exc.retry_action,
            },
        ) from exc

    @application.get("/api/targets")
    def list_targets() -> dict[str, object]:
        require_configuration()
        return {"targets": [target_response(target) for target in targets.list()]}

    @application.post("/api/targets", status_code=status.HTTP_201_CREATED)
    def create_target(definition: TargetDefinition) -> dict[str, object]:
        require_configuration()
        return target_response(targets.create(definition))

    @application.put("/api/targets/{target_id}")
    def save_target(target_id: str, definition: TargetDefinition) -> dict[str, object]:
        require_configuration()
        target_or_404(target_id)
        return target_response(targets.update(target_id, definition))

    @application.post("/api/targets/{target_id}/install")
    def install_target(target_id: str) -> dict[str, object]:
        require_configuration()
        target = target_or_404(target_id)
        if not target.enabled:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "target_disabled",
                    "message": "A disabled target cannot be installed.",
                    "retry_action": "Enable the target, then install it.",
                },
            )
        generated = generate_command(target.id, target.definition)
        try:
            adapter.install(target.id, generated)
        except TargetArtifactError as exc:
            artifact_failure(target.id, "install", exc)
        targets.clear_error(target.id, "install")
        return target_response(target_or_404(target.id))

    @application.post("/api/targets/{target_id}/disable")
    def disable_target(target_id: str) -> dict[str, object]:
        require_configuration()
        target = target_or_404(target_id)
        generated = generate_command(target.id, target.definition)
        try:
            adapter.remove(target.id, generated)
        except TargetArtifactError as exc:
            artifact_failure(target.id, "disable", exc)
        return target_response(targets.set_enabled(target.id, False))

    @application.post("/api/targets/{target_id}/enable")
    def enable_target(target_id: str) -> dict[str, object]:
        require_configuration()
        target_or_404(target_id)
        return target_response(targets.set_enabled(target_id, True))

    @application.delete("/api/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
    def remove_target(target_id: str) -> Response:
        require_configuration()
        target = target_or_404(target_id)
        generated = generate_command(target.id, target.definition)
        try:
            adapter.remove(target.id, generated)
        except TargetArtifactError as exc:
            artifact_failure(target.id, "remove", exc)
        targets.delete(target.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


def _new_provider_client(timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=min(5.0, timeout_seconds),
            read=timeout_seconds,
            write=min(5.0, timeout_seconds),
            pool=min(5.0, timeout_seconds),
        )
    )


app = create_app()
