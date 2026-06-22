from types import SimpleNamespace

from src import doctor
from src.doctor import has_failures, has_warnings, run_health_checks


def test_health_checks_report_warnings_without_network(tmp_path, monkeypatch):
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    monkeypatch.delenv("KALSHI_API_SECRET", raising=False)
    monkeypatch.setenv("KALSHI_SANDBOX", "true")

    checks = run_health_checks(
        env_path=tmp_path / ".env",
        db_path=tmp_path / "data" / "marketedge.db",
        dashboard_path=tmp_path / "web" / "data" / "missing.json",
        required_modules=("json",),
    )

    statuses = {check.name: check.status for check in checks}
    assert statuses["module:json"] == "ok"
    assert statuses["env"] == "warn"
    assert statuses["kalshi_credentials"] == "warn"
    assert statuses["sandbox"] == "ok"
    assert statuses["storage"] == "ok"
    assert statuses["dashboard_data"] == "warn"
    assert has_warnings(checks)
    assert not has_failures(checks)


def test_health_checks_fail_for_missing_dependency(tmp_path):
    checks = run_health_checks(
        env_path=tmp_path / ".env",
        db_path=tmp_path / "state.db",
        dashboard_path=tmp_path / "dashboard.json",
        required_modules=("definitely_missing_marketedge_dependency",),
    )

    assert has_failures(checks)
    assert checks[1].name == "module:definitely_missing_marketedge_dependency"
    assert checks[1].status == "fail"


def test_python_health_check_accepts_ci_support_floor(monkeypatch):
    monkeypatch.setattr(doctor.sys, "version_info", SimpleNamespace(major=3, minor=10))

    check = doctor._check_python()

    assert check.status == "ok"
    assert check.message == "Python 3.10 is supported."


def test_python_health_check_rejects_versions_below_ci_floor(monkeypatch):
    monkeypatch.setattr(doctor.sys, "version_info", SimpleNamespace(major=3, minor=9))

    check = doctor._check_python()

    assert check.status == "fail"
    assert check.remediation == "Use Python 3.10 or newer."
