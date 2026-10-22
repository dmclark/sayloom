import re
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError

from local_text.admin import _alembic_config
from local_text.app import create_app
from local_text.config import Profile, Settings
from local_text.database import ApplicationDatabase
from local_text.prompt_store import PromptStore
from local_text.target_adapter import InstallationState, TargetAdapter, TargetArtifactError
from local_text.target_store import TargetStore
from local_text.targets import INITIAL_TARGETS, SendStrategy, TargetDefinition, generate_command


def definition(**changes: object) -> TargetDefinition:
    values = {
        "display_name": "Synthetic Editor",
        "application_name": "Synthetic Editor",
        "application_bundle_id": "example.synthetic.editor",
        "icon": "🧵",
        "send_strategy": SendStrategy.SYNTHETIC_PASTE,
    }
    values.update(changes)
    return TargetDefinition(**values)


def test_target_definition_is_bounded_and_rejects_command_metadata_injection() -> None:
    with pytest.raises(ValidationError):
        definition(display_name="Synthetic\n# @raycast.title Injected")
    with pytest.raises(ValidationError):
        definition(application_bundle_id="/Applications/Synthetic.app")
    with pytest.raises(ValidationError):
        definition(send_strategy="arbitrary_script")


def test_generation_is_deterministic_outgoing_only_and_never_submits() -> None:
    first = generate_command("synthetic", definition())
    second = generate_command("synthetic", definition())

    assert first == second
    assert first.sha256
    assert first.content.count("/api/outgoing-state") == 1
    assert "/api/outgoing-delivery" not in first.content
    assert "raw_text" not in first.content
    assert "cleaned_text" not in first.content
    assert "outgoing_text" in first.content
    assert "waiting_for_evidence" not in first.content
    assert "sleep 0.25" not in first.content
    assert 'if [ "$http_status" = "409" ]' not in first.content
    assert "kp:return" not in first.content
    assert "key code 36" not in first.content
    assert "LC_ALL=en_US.UTF-8 /usr/bin/pbcopy" in first.content
    assert 'copy_utf8_to_clipboard < "$clipboard_backup"' in first.content
    subprocess.run(["/bin/sh", "-n"], input=first.content, text=True, check=True)

    iterm = generate_command("synthetic-iterm", definition(send_strategy=SendStrategy.ITERM_WRITE))
    assert 'tell application "Synthetic Editor"' in iterm.content
    assert "write text outgoingText newline NO" in iterm.content
    assert 'pbcopy < "$outgoing_file"' not in iterm.content
    subprocess.run(["/bin/sh", "-n"], input=iterm.content, text=True, check=True)


def test_stable_commands_coexist_with_development_targets(initialized_settings, tmp_path):
    directory = tmp_path / "raycast"
    development = generate_command("amp", definition())
    TargetAdapter(directory).install("amp", development)
    settings = replace(initialized_settings, stable_instance=True, raycast_directory=directory)
    with TestClient(create_app(settings)) as client:
        result = client.post("/api/targets/amp/install")
        result.raise_for_status()
        stable = (directory / "sayloom-stable-target-amp.sh").read_text()
        assert "# @raycast.title Stable: Send to Amp" in stable
        assert "http://127.0.0.1:7532" in stable and ":7523" not in stable
        assert (directory / "sayloom-target-amp.sh").read_text() == development.content
        assert ":7523" in development.content
        client.post("/api/targets/amp/disable").raise_for_status()
        assert not (directory / "sayloom-stable-target-amp.sh").exists()
        assert (directory / "sayloom-target-amp.sh").read_text() == development.content


def test_adapter_installs_exact_preview_idempotently_and_refuses_collisions(
    tmp_path: Path,
) -> None:
    adapter = TargetAdapter(tmp_path / "commands")
    generated = generate_command("synthetic", definition())
    path = tmp_path / "commands/sayloom-target-synthetic.sh"

    assert adapter.observe("synthetic", generated).installation is InstallationState.NOT_INSTALLED
    assert adapter.install("synthetic", generated).installation is InstallationState.INSTALLED
    assert path.read_text() == generated.content
    assert path.stat().st_mode & 0o777 == 0o700
    assert adapter.install("synthetic", generated).installation is InstallationState.INSTALLED

    changed = generate_command("synthetic", definition(display_name="Changed Synthetic"))
    assert adapter.observe("synthetic", changed).installation is InstallationState.NEEDS_UPDATE
    assert adapter.install("synthetic", changed).installation is InstallationState.INSTALLED
    assert path.read_text() == changed.content

    adapter.remove("synthetic", changed)
    assert not path.exists()
    path.write_text("#!/bin/sh\n# unrelated local file\n")
    with pytest.raises(TargetArtifactError) as rejected:
        adapter.install("synthetic", generated)
    assert rejected.value.code == "unrelated_artifact"
    assert path.read_text() == "#!/bin/sh\n# unrelated local file\n"


def test_adapter_refuses_unrelated_links_without_mutation(tmp_path: Path) -> None:
    directory = tmp_path / "commands"
    directory.mkdir()
    unrelated = tmp_path / "unrelated.sh"
    unrelated.write_text("unrelated\n")
    destination = directory / "sayloom-target-synthetic.sh"
    destination.symlink_to(unrelated)
    adapter = TargetAdapter(directory)

    with pytest.raises(TargetArtifactError):
        adapter.remove("synthetic", generate_command("synthetic", definition()))

    assert destination.is_symlink()
    assert destination.resolve() == unrelated
    assert unrelated.read_text() == "unrelated\n"


def test_seed_creates_only_the_four_approved_managed_targets(
    initialized_settings,
) -> None:
    store = TargetStore(ApplicationDatabase(initialized_settings.database_path))

    assert store.seed_defaults() == 0
    records = store.list()
    assert [record.id for record in records] == [target_id for target_id, _ in INITIAL_TARGETS]
    assert [record.display_name for record in records] == [
        "Amp",
        "iTerm",
        "Supacode",
        "VS Code",
    ]


def test_api_save_install_regenerate_disable_remove_and_outgoing_separation(
    initialized_settings, tmp_path: Path
) -> None:
    command_directory = tmp_path / "raycast"
    settings = replace(initialized_settings, raycast_directory=command_directory)
    client = TestClient(create_app(settings))
    outgoing = {
        "cleanup_enabled": True,
        "original_text": "synthetic original",
        "prepared_text": "synthetic prepared",
        "outgoing_text": "synthetic prepared",
        "outgoing_kind": "prepared",
        "status": "prepared",
    }
    assert client.put("/api/outgoing-state", json=outgoing).status_code == 200
    assert client.get("/api/outgoing-state").json()["outgoing_text"] == "synthetic prepared"

    created = client.post("/api/targets", json=definition().model_dump(mode="json"))
    assert created.status_code == 201
    target = created.json()
    target_id = target["id"]
    command_path = command_directory / f"sayloom-target-{target_id}.sh"
    assert target["state"] == "not_installed"
    assert target["availability"] == "not_verified"
    assert target["permission"] == "not_verified"
    assert not command_path.exists()

    installed = client.post(f"/api/targets/{target_id}/install")
    assert installed.status_code == 200
    assert installed.json()["installation"] == "installed"
    assert command_path.read_text() == installed.json()["preview"]

    changed_definition = definition(display_name="Changed Synthetic")
    saved = client.put(f"/api/targets/{target_id}", json=changed_definition.model_dump(mode="json"))
    assert saved.status_code == 200
    assert saved.json()["installation"] == "needs_update"
    assert command_path.read_text() != saved.json()["preview"]

    regenerated = client.post(f"/api/targets/{target_id}/install")
    assert regenerated.json()["installation"] == "installed"
    assert command_path.read_text() == regenerated.json()["preview"]

    disabled = client.post(f"/api/targets/{target_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["state"] == "disabled"
    assert not command_path.exists()
    assert client.get("/api/outgoing-state").json()["outgoing_text"] == "synthetic prepared"

    enabled = client.post(f"/api/targets/{target_id}/enable")
    assert enabled.json()["state"] == "not_installed"
    assert not command_path.exists()
    removed = client.delete(f"/api/targets/{target_id}")
    assert removed.status_code == 204
    assert client.get("/api/outgoing-state").json()["outgoing_text"] == "synthetic prepared"
    assert client.get(f"/api/targets/{target_id}").status_code == 405
    assert all(item["id"] != target_id for item in client.get("/api/targets").json()["targets"])


def test_collision_error_is_sanitized_persistent_and_non_destructive(
    initialized_settings, tmp_path: Path
) -> None:
    command_directory = tmp_path / "raycast"
    settings = replace(initialized_settings, raycast_directory=command_directory)
    client = TestClient(create_app(settings))
    target = client.get("/api/targets").json()["targets"][0]
    command_directory.mkdir()
    collision = command_directory / f"sayloom-target-{target['id']}.sh"
    collision.write_text("unrelated synthetic command\n")

    rejected = client.post(f"/api/targets/{target['id']}/install")

    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "unrelated_artifact"
    assert collision.read_text() == "unrelated synthetic command\n"
    persisted = next(
        item for item in client.get("/api/targets").json()["targets"] if item["id"] == target["id"]
    )
    assert persisted["state"] == "collision"
    assert persisted["errors"][0]["operation"] == "install"
    assert str(command_directory) not in rejected.text


def test_targets_surface_has_accessible_grid_and_modal_editor(
    initialized_settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    page = client.get("/").text
    script = client.get("/static/app.js").text
    stylesheet = client.get("/static/app.css").text

    assert '<button id="nav-settings"' in page
    assert page.index('id="correction-settings-title"') < page.index('id="targets-title"')
    assert 'role="list" aria-label="Saved targets"' in page
    assert '<button id="new-target" class="target-add-tile"' in page
    assert '<dialog id="target-dialog"' in page
    assert '<form id="target-detail"' in page
    assert 'id="save-target"' in page
    assert 'id="install-target"' in page
    assert "Saving changes only the durable definition" in page
    assert "Raycast and you own its hotkey" in page
    assert page.count("Outgoing is unchanged") >= 1
    assert 'aria-label="Generated Raycast command preview"' in page
    assert 'aria-label="Target operation errors"' in page
    assert 'window.confirm("Discard unsaved target definition changes?")' in script
    assert 'window.addEventListener("beforeunload"' in script
    assert "elements.targetDialog.showModal()" in script
    assert 'elements.targetDialog.addEventListener("cancel"' in script
    assert '!target || target.installation === "not_installed"' in script
    assert "grid-template-columns: repeat(auto-fill, minmax(210px, 1fr))" in stylesheet
    assert ".target-dialog::backdrop" in stylesheet
    narrow = stylesheet.split("@media (max-width: 760px)", maxsplit=1)[1]
    assert ".target-grid { grid-template-columns: 1fr;" in narrow


def test_bundle_id_pattern_is_valid_under_browser_v_semantics(
    initialized_settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    page = client.get("/").text
    match = re.search(r'id="target-bundle-id"[^>]+pattern="([^"]+)"', page)

    assert match is not None
    result = subprocess.run(
        [
            "node",
            "-e",
            """
const pattern = new RegExp(`^(?:${process.argv[1]})$`, "v");
const values = process.argv.slice(2).map((value) => pattern.test(value));
process.stdout.write(JSON.stringify(values));
""",
            match.group(1),
            "example.synthetic.editor",
            "com.example-editor.app",
            "not-a-bundle-id",
            ".example",
            "example.",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == "[true,true,false,false,false]"


def test_target_implementation_contains_no_predecessor_integration_identifiers() -> None:
    root = Path(__file__).parent.parent
    implementation = "\n".join(
        (root / path).read_text().lower()
        for path in (
            "src/local_text/targets.py",
            "src/local_text/target_store.py",
            "src/local_text/target_adapter.py",
            "src/local_text/static/index.html",
            "src/local_text/static/app.js",
        )
    )

    assert "voiceitt bridge" not in implementation
    assert "predecessor" not in implementation
    assert "target chooser" not in implementation
    assert "hotkey_value" not in implementation


def test_migration_upgrades_prompt_database_without_startup_or_data_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "upgrade.sqlite3"
    database = ApplicationDatabase(database_path)
    command.upgrade(_alembic_config(database.url), "0001_gate2_prompt_core")
    PromptStore(database).seed_default()
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM app_settings WHERE key = 'preparation_default'")
        connection.execute(
            "INSERT INTO app_settings (key, value_json, updated_at) "
            "VALUES ('cleanup_enabled_by_default', 'true', CURRENT_TIMESTAMP)"
        )
        before = connection.execute("SELECT system_text FROM prompt_versions").fetchall()

    settings = Settings(Profile.DEVELOPMENT, database_path=database_path)
    client = TestClient(create_app(replace(settings, raycast_directory=tmp_path / "commands")))
    assert client.get("/health").status_code == 503
    with sqlite3.connect(database_path) as connection:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0001_gate2_prompt_core"
        )

    command.upgrade(_alembic_config(database.url), "head")
    TargetStore(database).seed_defaults()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT system_text FROM prompt_versions").fetchall() == before
        assert connection.execute("SELECT COUNT(*) FROM targets").fetchone()[0] == 4
