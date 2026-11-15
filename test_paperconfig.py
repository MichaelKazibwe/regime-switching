from __future__ import annotations

import pytest

from paperconfig import PaperConfigurationError, PaperRuntimeConfig


def test_paper_config_defaults_and_environment() -> None:
    config = PaperRuntimeConfig.from_env({})
    assert config.mode == "PAPER"
    assert config.live_trading_enabled is False
    assert config.broker_submission_enabled is False
    assert config.commission_rate == 0.0005
    assert config.slippage_rate == 0.001


def test_paper_config_reads_execution_cost_assumptions() -> None:
    config = PaperRuntimeConfig.from_env(
        {"PAPER_COMMISSION_RATE": "0.001", "PAPER_SLIPPAGE_RATE": "0.002"}
    )
    assert config.commission_rate == 0.001
    assert config.slippage_rate == 0.002


def test_smtp_password_is_hidden_from_config_repr() -> None:
    config = PaperRuntimeConfig.from_env(
        {
            "PAPER_SMTP_HOST": "smtp.example.com",
            "PAPER_SMTP_SENDER": "paper@example.com",
            "PAPER_ALERT_RECIPIENT": "operator@example.com",
            "PAPER_SMTP_USERNAME": "paper-user",
            "PAPER_SMTP_PASSWORD": "do-not-print-this",
        }
    )
    assert "do-not-print-this" not in repr(config)


@pytest.mark.parametrize(
    "environment",
    [
        {"TRADING_MODE": "LIVE"},
        {"LIVE_TRADING_ENABLED": "true"},
        {"BROKER_SUBMISSION_ENABLED": "1"},
        {"REBALANCE_INTERVAL_DAYS": "0"},
        {"MAXIMUM_PRICE_AGE_HOURS": "not-an-int"},
        {"TRADING_TIMEZONE": "Mars/Olympus_Mons"},
        {"PAPER_COMMISSION_RATE": "nan"},
        {"PAPER_SLIPPAGE_RATE": "0.2"},
        {"PAPER_SMTP_HOST": "smtp.example.com"},
        {"PAPER_SMTP_USERNAME": "operator"},
        {"PAPER_SMTP_USE_TLS": "maybe"},
    ],
)
def test_paper_config_rejects_unsafe_or_invalid_environment(
    environment: dict[str, str],
) -> None:
    with pytest.raises(PaperConfigurationError):
        PaperRuntimeConfig.from_env(environment)
