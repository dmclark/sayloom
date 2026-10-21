"""FastAPI application entry point."""

import re
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.exc import SQLAlchemyError

from local_text.cleanup import (
    GEMINI_37_FLASH,
    OPENAI_GPT_56_LUNA,
    OPENROUTER_ENDPOINTS,
    OPENROUTER_MODELS,
    OPENROUTER_QWEN,
    CleanupPartitionSchedule,
    CleanupRequest,
    CleanupResult,
    CleanupRoute,
    CleanupService,
    CorrectionMode,
    GeminiAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
    PreparationMode,
    SequentialCleanupProvider,
    lexical_repairs,
    missed_repair_sentences,
)
from local_text.config import Profile, Settings, load_settings
from local_text.database import ApplicationDatabase
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
            primary, secondary = (
                "OpenAI" if provider == "openai" else "Gemini"
                for provider, _model, _quota_group in self.routes
            )
            disclosure = {
                "summary": f"Paid {primary} → {secondary} fallback",
                "processing": (
                    f"Cleanup sends the current text and cleanup instruction to paid {primary} "
                    "for external processing."
                ),
                "fallback": (
                    f"Only after a qualifying {primary} failure, the same current text and cleanup "
                    f"instruction may be sent to paid {secondary}."
                ),
                "corpus": (
                    "Routine cleanup does not retain Original, Prepared, or provider payloads."
                ),
            }
        elif self.status == "openrouter_only":
            disclosure = {
                "summary": "Paid OpenRouter cleanup",
                "processing": (
                    "Cleanup sends current text and instructions through OpenRouter for paid "
                    "external processing, restricted to ZDR providers and any configured endpoint."
                ),
                "fallback": (
                    "After a qualifying failure, the next configured model may receive the same "
                    "text within the shared cleanup deadline. Failures preserve Original."
                    if len(self.routes) > 1
                    else "No model fallback. Failures preserve Original."
                ),
                "corpus": "Routine cleanup does not retain text or provider payloads.",
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
                PAID_DATA_ACKNOWLEDGEMENT
                if self.status in {"cross_provider", "openrouter_only"}
                else None
            ),
            "validation_error": self.validation_error,
            "disclosure": disclosure,
        }


def _cleanup_runtime_configuration(runtime: Settings) -> CleanupRuntimeConfiguration:
    if runtime.cleanup_route_order == "openrouter":
        models = runtime.openrouter_models or (
            (runtime.openrouter_model,) if runtime.openrouter_model else ()
        )
        error = None
        if not runtime.openrouter_api_key:
            error = "explicit_openrouter_credential_required"
        elif runtime.openrouter_model is not None and models != (runtime.openrouter_model,):
            error = "conflicting_openrouter_model_settings"
        elif not models or any(model not in OPENROUTER_MODELS for model in models):
            error = "unsupported_openrouter_models"
        elif len(models) > 2 or len(set(models)) != len(models):
            error = "one_or_two_distinct_openrouter_models_required"
        elif runtime.openrouter_endpoints and (
            len(runtime.openrouter_endpoints) != len(models)
            or any(
                endpoint not in OPENROUTER_ENDPOINTS for endpoint in runtime.openrouter_endpoints
            )
        ):
            error = "invalid_openrouter_endpoints"
        elif not runtime.openrouter_endpoints and any(model != OPENROUTER_QWEN for model in models):
            error = "explicit_openrouter_endpoints_required"
        elif runtime.paid_data_acknowledgement != PAID_DATA_ACKNOWLEDGEMENT:
            error = "paid_data_acknowledgement_required"
        if error:
            return CleanupRuntimeConfiguration("invalid", validation_error=error)
        return _configured_cleanup_routes(
            runtime,
            "openrouter_only",
            tuple(("openrouter", model, "openrouter-account") for model in models),
        )
    if runtime.cleanup_route_order is None:
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
    routes = (
        ("gemini", GEMINI_37_FLASH, runtime.gemini_quota_group_id or ""),
        ("openai", OPENAI_GPT_56_LUNA, runtime.openai_quota_group_id or ""),
    )
    if runtime.cleanup_route_order == "openai,gemini":
        routes = routes[::-1]
    return _configured_cleanup_routes(runtime, "cross_provider", routes)


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
    if runtime.cleanup_route_order not in {CROSS_PROVIDER_ROUTE_ORDER, "openai,gemini"}:
        return "route_order_must_be_gemini_openai_or_openai_gemini"
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


class PersonalCorrectionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_mode: Literal["conservative", "smart", "user_confirmed"]
    prompt_version_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_provenance(self):
        if (self.source_mode == "user_confirmed") != (self.prompt_version_id is None):
            raise ValueError(
                "manual confirmation has no processing prompt; generation requires one"
            )
        return self


class PersonalCorrectionCandidateRequest(PersonalCorrectionProvenance):
    before_text: str = Field(max_length=100_000)
    after_text: str = Field(max_length=100_000)
    correction_contract_version: str = Field(pattern=r"^personal-correction-v1$")


class PersonalCorrectionReplacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["replacement"]
    observed_text: str = Field(min_length=1, max_length=200)
    intended_text: str = Field(min_length=1, max_length=200)


class PersonalCorrectionApprovalRequest(PersonalCorrectionProvenance):
    approval_id: UUID
    correction_contract_version: Literal["personal-correction-v1"]
    observed_sentence: str | None = Field(default=None, max_length=500)
    intended_sentence: str | None = Field(default=None, max_length=500)
    applicability_context: str | None = Field(default=None, max_length=500)
    mapping: PersonalCorrectionReplacementRequest | None = None
    mappings: list[PersonalCorrectionReplacementRequest] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selection(self):
        if (self.mapping is None) == (self.mappings is None):
            raise ValueError("provide either a replacement or selected replacements")
        return self


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
            for route_index, (provider_id, model, quota_group_id) in enumerate(
                cleanup_configuration.routes
            ):
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
                    else OpenRouterAdapter(
                        runtime.openrouter_api_key or "",
                        model,
                        client,
                        serving_endpoint=(
                            runtime.openrouter_endpoints[route_index]
                            if runtime.openrouter_endpoints
                            else None
                        ),
                        quota_group_id=quota_group_id,
                    )
                    if provider_id == "openrouter"
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
                provider_id=cleanup_configuration.routes[0][0],
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
                headers={"Cache-Control": "no-store"},
                content={
                    "detail": {
                        "code": "invalid_personal_correction_request",
                        "message": "The request did not match the Personal corrections contract.",
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
    def browser_config() -> dict[str, object]:
        require_configuration()
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
            "active_prompt_version_id": prompts.active().id,
        }

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
            raise HTTPException(
                status_code=404,
                detail="Personal correction does not exist",
                headers={"Cache-Control": "no-store"},
            )
        if isinstance(exc, PersonalCorrectionRevisionConflictError):
            raise HTTPException(
                status_code=409,
                headers={"Cache-Control": "no-store"},
                detail={
                    "code": "stale_personal_correction_revision",
                    "message": "This Personal correction changed since it was opened.",
                    "retry_action": "Reload Personal corrections and apply the edit again.",
                },
            )
        if isinstance(exc, PersonalCorrectionConflictError):
            raise HTTPException(
                status_code=409,
                headers={"Cache-Control": "no-store"},
                detail={
                    "code": "personal_correction_conflict",
                    "message": "A conflicting Personal correction already exists.",
                    "retry_action": "Reload Personal corrections and edit the existing entry.",
                },
            )
        raise HTTPException(
            status_code=422,
            headers={"Cache-Control": "no-store"},
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

    @application.post("/api/personal-corrections/candidates")
    def personal_correction_candidates(
        request: PersonalCorrectionCandidateRequest, response: Response
    ) -> dict[str, object]:
        require_configuration()
        response.headers["Cache-Control"] = "no-store"
        try:
            active_prompt_version_id = prompts.active().id
        except SeedStateError as exc:
            raise HTTPException(
                status_code=409,
                headers={"Cache-Control": "no-store"},
                detail={
                    "code": "stale_personal_correction_result",
                    "message": "The result used by this review is no longer current.",
                    "retry_action": "Run correction again before opening this review.",
                },
            ) from exc
        if (
            request.source_mode != "user_confirmed"
            and request.prompt_version_id != active_prompt_version_id
        ):
            raise HTTPException(
                status_code=409,
                headers={"Cache-Control": "no-store"},
                detail={
                    "code": "stale_personal_correction_result",
                    "message": "The result used by this review is no longer current.",
                    "retry_action": "Run correction again before opening this review.",
                },
            )
        observed_sentence, intended_sentence = missed_repair_sentences(
            request.before_text, request.after_text
        )
        return {
            "candidates": [
                repair.model_dump(mode="json")
                for repair in lexical_repairs(request.before_text, request.after_text)
            ],
            "observed_sentence": observed_sentence,
            "intended_sentence": intended_sentence,
            "applicability_context": None,
        }

    @application.post("/api/personal-corrections/episodes")
    def approve_personal_correction(
        request: PersonalCorrectionApprovalRequest, response: Response
    ) -> dict[str, object]:
        require_configuration()
        response.headers["Cache-Control"] = "no-store"
        try:
            active_prompt_version_id = prompts.active().id
        except SeedStateError as exc:
            raise HTTPException(
                status_code=409,
                headers={"Cache-Control": "no-store"},
                detail={
                    "code": "stale_personal_correction_result",
                    "message": "The result used by this review is no longer current.",
                    "retry_action": "Run correction again before opening this review.",
                },
            ) from exc
        if (
            request.source_mode != "user_confirmed"
            and request.prompt_version_id != active_prompt_version_id
        ):
            raise HTTPException(
                status_code=409,
                headers={"Cache-Control": "no-store"},
                detail={
                    "code": "stale_personal_correction_result",
                    "message": "The result used by this review is no longer current.",
                    "retry_action": "Run correction again before opening this review.",
                },
            )
        try:
            record, created = personal_corrections.approve_replacements(
                approval_id=str(request.approval_id),
                mappings=tuple(
                    (mapping.observed_text, mapping.intended_text)
                    for mapping in (request.mappings or [request.mapping])
                ),
                observed_sentence=request.observed_sentence,
                intended_sentence=request.intended_sentence,
                applicability_context=request.applicability_context,
                source_mode=request.source_mode,
                prompt_version_id=request.prompt_version_id,
                correction_contract_version=request.correction_contract_version,
            )
        except PersonalCorrectionError as exc:
            personal_correction_failure(exc)
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=503,
                headers={"Cache-Control": "no-store"},
                detail={
                    "code": "personal_correction_save_unavailable",
                    "message": "The Personal Correction could not be saved.",
                    "retry_action": "Retry while this review is current.",
                },
            ) from exc
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        result = personal_correction_response(record)
        # Preserve the existing single-replacement API response for its callers.
        if request.mapping is not None:
            result["mapping"] = result["mappings"][0]
            result["correction"] = result["corrections"][0]
        return result

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
        return state.read().public()

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
