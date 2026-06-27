from click.testing import CliRunner

from src.cli import cli
from src.safety import evaluate_live_trading_gate


def _gate(**overrides):
    kwargs = dict(
        live=True,
        api_key="key",
        api_secret="secret",
        confirmed=True,
        allow_live_env="true",
        kill_switch_env=None,
    )
    kwargs.update(overrides)
    return evaluate_live_trading_gate(**kwargs)


def test_dry_run_is_always_allowed():
    decision = evaluate_live_trading_gate(
        live=False,
        api_key="",
        api_secret="",
        confirmed=False,
        allow_live_env=None,
    )
    assert decision.allowed is True


def test_live_allowed_when_every_gate_satisfied():
    assert _gate().allowed is True


def test_live_blocked_without_explicit_enablement():
    decision = _gate(allow_live_env=None)
    assert decision.allowed is False
    assert "MARKETEDGE_ALLOW_LIVE" in decision.reason


def test_live_blocked_without_api_key():
    decision = _gate(api_key="")
    assert decision.allowed is False
    assert "KALSHI_API_KEY" in decision.reason


def test_live_blocked_without_api_secret():
    decision = _gate(api_secret="")
    assert decision.allowed is False
    assert "KALSHI_API_SECRET" in decision.reason


def test_live_blocked_without_operator_confirmation():
    decision = _gate(confirmed=False)
    assert decision.allowed is False
    assert "--confirm-live" in decision.reason


def test_kill_switch_overrides_full_enablement():
    decision = _gate(kill_switch_env="true")
    assert decision.allowed is False
    assert "kill switch" in decision.reason.lower()


def test_cli_trade_live_fails_closed_with_no_credentials(monkeypatch):
    # No opt-in, no credentials, no confirmation: the most common accidental
    # invocation must exit non-zero without constructing a live client.
    monkeypatch.delenv("MARKETEDGE_ALLOW_LIVE", raising=False)
    monkeypatch.delenv("MARKETEDGE_KILL_SWITCH", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["trade", "--live"])
    assert result.exit_code == 1
    assert "Live trading blocked" in result.output
