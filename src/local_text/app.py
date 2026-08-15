"""FastAPI application entry point."""

from dataclasses import asdict
from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from local_text.cleanup import CleanupRequest, CleanupResult, CleanupService, GeminiProvider
from local_text.config import Settings, load_settings
from local_text.state import OutgoingStateStore, OutgoingStateUpdate

STATIC_DIRECTORY = Path(__file__).parent / "static"
INDEX_TEMPLATE = (STATIC_DIRECTORY / "index.html").read_text()


def create_app(
    settings: Settings | None = None,
    cleanup_service: CleanupService | None = None,
) -> FastAPI:
    runtime = settings or load_settings()
    application = FastAPI(title=runtime.display_name)
    state = OutgoingStateStore(cleanup_enabled=runtime.cleanup_enabled_by_default)
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
    def health() -> dict[str, str]:
        return {"status": "ok", "profile": runtime.profile}

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
        return {
            "display_name": runtime.display_name,
            "profile": runtime.profile,
            "cleanup_enabled_by_default": runtime.cleanup_enabled_by_default,
            "cleanup_available": provider is not None or cleanup_service is not None,
            "cleanup_model": runtime.gemini_model,
        }

    @application.post("/api/cleanup", response_model=CleanupResult)
    async def clean_text(request: CleanupRequest) -> CleanupResult:
        return await cleanup.clean(request)

    @application.get("/api/outgoing-state")
    def outgoing_state() -> dict[str, object]:
        return asdict(state.read())

    @application.put("/api/outgoing-state")
    def publish_outgoing_state(update: OutgoingStateUpdate) -> dict[str, object]:
        return asdict(state.update(update))

    @application.delete("/api/outgoing-state")
    def clear_outgoing_state() -> dict[str, object]:
        return asdict(state.clear())

    return application


app = create_app()
