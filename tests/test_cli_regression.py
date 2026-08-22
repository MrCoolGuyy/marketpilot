import subprocess
import sys
import os


def test_cli_banner_no_nameerror():
    """Verify uv run marketpilot doesn't fail with NameError or AttributeError."""
    result = subprocess.run(
        [sys.executable, "-m", "marketpilot.cli"], capture_output=True, text=True
    )
    # The banner prints and exits with 0
    assert result.returncode == 0
    assert "Foundation loaded" in result.stderr or "Foundation loaded" in result.stdout


def test_cli_help():
    """Verify --help command works."""
    result = subprocess.run(
        [sys.executable, "-m", "marketpilot.cli", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "MarketPilot CLI - Command Reference" in result.stdout
    assert "daemon" in result.stdout


def test_cli_daemon(tmp_path):
    """Verify daemon dry-run doesn't crash."""
    result = subprocess.run(
        [sys.executable, "-m", "marketpilot.cli", "daemon"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "Orders submitted: 0" in result.stdout
    assert "Daemon startup sequence verified successfully in dry-run mode." in result.stdout


def test_cli_dashboard_bootstrap():
    """Verify dashboard CLI doesn't throw ImportError for create_app."""
    try:
        # We need to unbuffer stdout so we can catch print statements if it times out
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "marketpilot.cli",
                "dashboard",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
            ],
            capture_output=True,
            text=True,
            timeout=2,  # It will block, so we timeout
            env=env,
        )
        assert "ImportError" not in result.stderr
        output = result.stdout + result.stderr
        assert "Starting MarketPilot Dashboard" in output
    except subprocess.TimeoutExpired as e:
        # We expect a timeout since the server runs indefinitely
        stderr_str = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        stdout_str = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        assert "ImportError" not in stderr_str
        output = stdout_str + stderr_str
        assert "Starting MarketPilot Dashboard" in output


def test_cli_smoke_phase4():
    """Verify smoke_test_phase4.py configuration doesn't crash."""
    result = subprocess.run(
        [sys.executable, "scripts/smoke_test_phase4.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "AttributeError" not in result.stderr
    assert "TOTAL ORDERS SUBMITTED: 0" in result.stderr
