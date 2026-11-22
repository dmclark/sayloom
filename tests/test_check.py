"""Full-check orchestration and safe, non-fail-fast pytest progress."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mode", ["", "--full", "--quick"])
@pytest.mark.parametrize("failure", ["", "ruff", "pytest", "node"])
def test_check_phases_and_exit_status(tmp_path: Path, failure: str, mode: str) -> None:
    # Fake only the external commands here; reporting below runs real pytest.
    executable = tmp_path / "command"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['run', 'python']:\n"
        "    os.execv(sys.executable, [sys.executable, *args[2:]])\n"
        "name = 'node' if sys.argv[0].endswith('node') else "
        "(args[1] if args[0] == 'run' else args[0])\n"
        "print('COMMAND ' + name, flush=True)\n"
        "sys.exit(7 if name == os.environ['FAIL_CHECK'] else 0)\n"
    )
    executable.chmod(0o755)
    for name in ("uv", "node"):
        (tmp_path / name).symlink_to(executable)
    result = subprocess.run(
        ["bash", str(REPOSITORY / "scripts/check"), *([mode] if mode else [])],
        cwd=REPOSITORY,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "FAIL_CHECK": failure},
        capture_output=True,
        text=True,
        timeout=30,
    )
    selected_failure = failure and not (mode == "--quick" and failure == "pytest")
    assert result.returncode == (7 if selected_failure else 0), result.stderr
    phases = [
        ("Dependencies", "sync"),
        ("Lint", "ruff"),
        *([] if mode == "--quick" else [("Pytest", "pytest")]),
        ("JavaScript", "node"),
    ]
    for phase, command in phases:
        assert f"[check] {phase} started (" in result.stdout
        assert f"COMMAND {command}" in result.stdout
        assert f"[check] {phase} finished: exit " in result.stdout
        if command == failure:
            break
    else:
        assert "[check] JavaScript finished: exit 0" in result.stdout
    assert f"[check] Finished: exit {result.returncode}" in result.stdout
    assert "s phase," in result.stdout and "s elapsed)" in result.stdout
    if mode == "--quick":
        assert "COMMAND pytest" not in result.stdout
        assert "Pytest started" not in result.stdout
    elif failure == "pytest":
        assert "JavaScript started" not in result.stdout


def test_pytest_failure_is_safe_and_visible_before_slow_test_finishes(tmp_path: Path) -> None:
    shutil.copy2(REPOSITORY / "tests/conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_progress.py").write_text(
        "import time\n"
        "import pytest\n"
        "@pytest.mark.parametrize('value', ['synthetic-private-parameter'])\n"
        "def test_failure(value):\n"
        "    raise ValueError('synthetic-private-message')\n"
        "def test_slow():\n"
        "    time.sleep(0.4)\n"
        "    print('SLOW FINISHED', flush=True)\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-s", "--tb=no", str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stderr
    immediate = next(line for line in result.stdout.splitlines() if "[pytest] FAILED" in line)
    assert "test_progress.py::test_failure" in immediate
    assert "ValueError" in immediate and "call," in immediate
    assert "synthetic-private" not in immediate
    assert result.stdout.index(immediate) < result.stdout.index("SLOW FINISHED")
    assert "1 failed, 1 passed" in result.stdout


def test_full_check_restores_sigint_for_pytest(tmp_path: Path) -> None:
    executable = tmp_path / "uv"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, signal, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['run', 'python']:\n"
        "    os.execv(sys.executable, [sys.executable, *args[2:]])\n"
        "if args == ['run', 'pytest']:\n"
        "    os.kill(os.getpid(), signal.SIGINT)\n"
    )
    executable.chmod(0o755)
    # Match the orb's inherited ignored SIGINT without changing this pytest process.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, signal; signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "os.execvp('bash', ['bash', '" + str(REPOSITORY / "scripts/check") + "'])",
        ],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 130, result.stdout + result.stderr
    assert "Pytest finished: exit 130" in result.stdout
    assert "JavaScript started" not in result.stdout


def test_lifecycle_cache_preparation_failure_stops_once_before_installs(tmp_path: Path) -> None:
    (tmp_path / "conftest.py").write_text(
        "import runpy\n"
        f"fixtures = runpy.run_path({str(REPOSITORY / 'tests/test_stable.py')!r})\n"
        "dependency_cache_home = fixtures['dependency_cache_home']\n"
        "shared_dependency_cache = fixtures['shared_dependency_cache']\n"
    )
    (tmp_path / "test_install.py").write_text(
        "from pathlib import Path\n"
        "def test_first():\n    Path('install-attempted').touch()\n"
        "def test_second():\n    Path('install-attempted').touch()\n"
    )
    executable = tmp_path / "uv"
    calls = tmp_path / "preparation-calls"
    executable.write_text(
        f"#!{sys.executable}\n"
        "from pathlib import Path\n"
        f"with Path({str(calls)!r}).open('a') as output:\n    output.write('sync\\n')\n"
        "print('synthetic-private-download-error')\n"
        "raise SystemExit(9)\n"
    )
    executable.chmod(0o755)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(tmp_path)],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert calls.read_text() == "sync\n"
    assert not (tmp_path / "install-attempted").exists()
    output = result.stdout + result.stderr
    assert "[lifecycle cache] Preparing locked dependencies" in output
    assert output.count("Lifecycle cache preparation failed after") == 1
    assert "exit 9" in output
    assert "synthetic-private-download-error" not in output
