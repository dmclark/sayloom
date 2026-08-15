from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.config import Profile, Settings


def test_health_reports_development_profile() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))

    assert client.get("/health").json() == {"status": "ok", "profile": "development"}


def test_development_page_identifies_development_brand() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))

    response = client.get("/")

    assert response.status_code == 200
    assert "Sayloom Development" in response.text


def test_release_profile_uses_release_brand() -> None:
    client = TestClient(create_app(Settings(Profile.RELEASE)))

    assert client.app.title == "Sayloom"
    assert client.get("/health").json()["profile"] == "release"
