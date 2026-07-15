"""Local readiness checks for Market Edge operators."""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

REQUIRED_MODULES = (
    "click",
    "dotenv",
    "httpx",
    "rich",
    "sqlalchemy",
    "textual",
    "websockets",
)
# Keep in sync with `requires-python` in pyproject.toml and the README badge.
MIN_PYTHON_VERSION = (3, 12)


@dataclass(frozen=True)
class HealthCheck:
    """One operator-facing readiness result."""

    name: str
    status: str
    message: str
    remediation: str = ""

    @property
    def is_failure(self) -> bool:
        return self.status == "fail"

    @property
    def is_warning(self) -> bool:
        return self.status == "warn"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "remediation": self.remediation,
        }


def run_health_checks(
    env_path: str | Path = ".env",
    db_path: str | Path | None = None,
    dashboard_path: str | Path = "web/data/backtest-summary.json",
    required_modules: Iterable[str] = REQUIRED_MODULES,
) -> List[HealthCheck]:
    """Return local setup checks without requiring network access."""
    env_file = Path(env_path)
    database_path = Path(
        str(db_path or os.getenv("MARKETEDGE_DB_PATH", "data/kalshi_quant.db"))
    )
    dashboard_file = Path(dashboard_path)

    checks: List[HealthCheck] = []
    checks.append(_check_python())
    checks.extend(_check_modules(required_modules))
    checks.append(_check_env_file(env_file))
    checks.append(_check_credentials())
    checks.append(_check_sandbox_mode())
    checks.append(_check_storage_path(database_path))
    checks.append(_check_dashboard_artifact(dashboard_file))
    return checks


def has_failures(checks: Iterable[HealthCheck]) -> bool:
    return any(check.is_failure for check in checks)


def has_warnings(checks: Iterable[HealthCheck]) -> bool:
    return any(check.is_warning for check in checks)


def _check_python() -> HealthCheck:
    current = (sys.version_info.major, sys.version_info.minor)
    minimum = f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}"
    if current >= MIN_PYTHON_VERSION:
        return HealthCheck(
            "python",
            "ok",
            f"Python {sys.version_info.major}.{sys.version_info.minor} is supported.",
        )
    return HealthCheck(
        "python",
        "fail",
        f"Python {sys.version_info.major}.{sys.version_info.minor} is too old.",
        f"Use Python {minimum} or newer.",
    )


def _check_modules(required_modules: Iterable[str]) -> List[HealthCheck]:
    checks: List[HealthCheck] = []
    for module in required_modules:
        if importlib.util.find_spec(module):
            checks.append(
                HealthCheck(f"module:{module}", "ok", f"{module} is importable.")
            )
        else:
            checks.append(
                HealthCheck(
                    f"module:{module}",
                    "fail",
                    f"{module} is not importable.",
                    "Install dependencies with `pip install -r requirements.txt`.",
                )
            )
    return checks


def _check_env_file(env_path: Path) -> HealthCheck:
    if env_path.exists():
        return HealthCheck("env", "ok", f"{env_path} exists.")
    return HealthCheck(
        "env",
        "warn",
        f"{env_path} is missing.",
        "Copy `.env.example` to `.env` before API-backed workflows.",
    )


def _check_credentials() -> HealthCheck:
    api_key = os.getenv("KALSHI_API_KEY", "")
    api_secret = os.getenv("KALSHI_API_SECRET", "")
    if api_key and api_secret:
        return HealthCheck(
            "kalshi_credentials",
            "ok",
            "Kalshi credentials are configured without exposing secret values.",
        )
    return HealthCheck(
        "kalshi_credentials",
        "warn",
        "Kalshi credentials are not fully configured.",
        "Dry-run, local backtest, and no-account dashboard workflows still work.",
    )


def _check_sandbox_mode() -> HealthCheck:
    sandbox = os.getenv("KALSHI_SANDBOX", "true").lower() == "true"
    if sandbox:
        return HealthCheck("sandbox", "ok", "Kalshi sandbox mode is enabled.")
    return HealthCheck(
        "sandbox",
        "warn",
        "Kalshi sandbox mode is disabled.",
        "Only use live mode with explicit operator approval and safety gates.",
    )


def _check_storage_path(db_path: Path) -> HealthCheck:
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return HealthCheck(
            "storage",
            "fail",
            f"Cannot create database directory {parent}: {exc}.",
            "Choose a writable MARKETEDGE_DB_PATH or fix directory permissions.",
        )

    if os.access(parent, os.W_OK):
        return HealthCheck("storage", "ok", f"SQLite directory {parent} is writable.")
    return HealthCheck(
        "storage",
        "fail",
        f"SQLite directory {parent} is not writable.",
        "Choose a writable MARKETEDGE_DB_PATH or fix directory permissions.",
    )


def _check_dashboard_artifact(path: Path) -> HealthCheck:
    if path.exists():
        return HealthCheck("dashboard_data", "ok", f"{path} exists.")
    return HealthCheck(
        "dashboard_data",
        "warn",
        f"{path} is missing.",
        "Generate it with `python -m src.cli backtest ... --json-out web/data/backtest-summary.json`.",
    )
