"""FastAPI application entry point."""

from dataclasses import asdict
from datetime import UTC
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from local_text.cleanup import CleanupRequest, CleanupResult, CleanupService, GeminiProvider
from local_text.config import Settings, load_settings
from local_text.database import ApplicationDatabase
from local_text.prompt_store import PromptNotFoundError, PromptRecord, PromptStore, SeedStateError
from local_text.state import OutgoingStateStore, OutgoingStateUpdate

STATIC_DIRECTORY = Path(__file__).parent / "static"
INDEX_TEMPLATE = (STATIC_DIRECTORY / "index.html").read_text()


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
) -> FastAPI:
    runtime = settings or load_settings()
    application = FastAPI(title=runtime.display_name)
    database = ApplicationDatabase(runtime.resolved_database_path)
    schema = database.schema_status()
    prompts = PromptStore(database)
    configuration_error: str | None = None
    cleanup_enabled = True
    if schema.ready:
        try:
            cleanup_enabled = prompts.cleanup_enabled_by_default()
            prompts.active()
        except SeedStateError as exc:
            configuration_error = str(exc)
    state = OutgoingStateStore(cleanup_enabled=cleanup_enabled)
    provider = (
        GeminiProvider(
            runtime.gemini_api_key,
            runtime.gemini_model,
            timeout_seconds=runtime.cleanup_timeout_seconds,
        )
        if runtime.gemini_api_key
        else None
    )
    cleanup = cleanup_service or CleanupService(
        provider=provider,
        model=runtime.gemini_model,
        timeout_seconds=runtime.cleanup_timeout_seconds,
    )
    application.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")

    @application.get("/health")
    def health(response: Response) -> dict[str, object]:
        ready = schema.ready and configuration_error is None
        if not ready:
            response.status_code = 503
        return {
            "status": "ok" if ready else "setup_required",
            "profile": runtime.profile,
            "database": {
                "state": schema.state,
                "current_revision": schema.current_revision,
                "expected_revision": schema.expected_revision,
            },
            "configuration_error": configuration_error,
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
        development_badge = (
            '<span class="development-badge" aria-label="Development profile">DEV</span>'
            if runtime.profile.value == "development"
            else ""
        )
        return (
            INDEX_TEMPLATE.replace("__DISPLAY_NAME__", escape(runtime.display_name))
            .replace("__PROFILE__", escape(runtime.profile.value))
            .replace("__DEVELOPMENT_BADGE__", development_badge)
        )

    @application.get("/api/config")
    def browser_config() -> dict[str, str | bool]:
        require_configuration()
        return {
            "display_name": runtime.display_name,
            "profile": runtime.profile,
            "cleanup_enabled_by_default": prompts.cleanup_enabled_by_default(),
            "cleanup_available": provider is not None or cleanup_service is not None,
            "cleanup_model": runtime.gemini_model,
        }

    @application.post("/api/cleanup", response_model=CleanupResult)
    async def clean_text(request: CleanupRequest) -> CleanupResult:
        require_configuration()
        return await cleanup.clean(request, prompts.active().system_text)

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
        return asdict(state.read())

    @application.put("/api/outgoing-state")
    def publish_outgoing_state(update: OutgoingStateUpdate) -> dict[str, object]:
        require_configuration()
        if update.cleanup_enabled != prompts.cleanup_enabled_by_default():
            prompts.set_cleanup_enabled_by_default(update.cleanup_enabled)
        return asdict(state.update(update))

    @application.delete("/api/outgoing-state")
    def clear_outgoing_state() -> dict[str, object]:
        require_configuration()
        return asdict(state.clear())

    return application


app = create_app()
