"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from local_text.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or load_settings()
    application = FastAPI(title=runtime.display_name)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "profile": runtime.profile}

    @application.get("/", response_class=HTMLResponse)
    def development_page() -> str:
        return f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>{runtime.display_name}</title></head>
  <body>
    <main><h1>{runtime.display_name}</h1><p>Local development runtime is healthy.</p></main>
  </body>
</html>"""

    return application


app = create_app()
