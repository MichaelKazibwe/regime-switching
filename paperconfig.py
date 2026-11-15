"""Validated configuration for the short-term paper deployment.

This module deliberately has no live-trading mode. Live execution needs a
separate deployment design and explicit authorization; setting an environment
variable cannot enable it here.
"""

from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from assetuniverse import PRODUCTION_ASSETS


class PaperConfigurationError(ValueError):
    """Raised when paper runtime configuration is unsafe or incomplete."""


def _positive_int(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PaperConfigurationError(f"{name} must be an integer.") from exc
    if parsed <= 0:
        raise PaperConfigurationError(f"{name} must be positive.")
    return parsed


def _boolean(name: str, value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise PaperConfigurationError(f"{name} must be a boolean value.")


@dataclass(frozen=True)
class PaperRuntimeConfig:
    """Runtime settings for an isolated, paper-only portfolio service."""

    state_database: Path = Path("var/paper-state.sqlite3")
    audit_log: Path = Path("var/paper-audit.jsonl")
    report_directory: Path = Path("var/paper-reports")
    dashboard_file: Path = Path("var/paper-dashboard.html")
    research_snapshot_directory: Path = Path("var/research-snapshots")
    alert_file: Path = Path("var/paper-alerts.jsonl")
    market_period: str = "15y"
    rebalance_interval_days: int = 21
    maximum_price_age_hours: int = 72
    initial_cash: float = 1_000_000.0
    cash_buffer_fraction: float = 0.01
    commission_rate: float = 0.0005
    slippage_rate: float = 0.001
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_sender: str | None = None
    smtp_recipient: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = field(default=None, repr=False)
    smtp_use_tls: bool = True
    timezone: str = "UTC"
    benchmark: str = "SPY"
    assets: tuple[str, ...] = tuple(PRODUCTION_ASSETS)
    mode: str = "PAPER"
    live_trading_enabled: bool = False
    broker_submission_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_database", Path(self.state_database))
        object.__setattr__(self, "audit_log", Path(self.audit_log))
        object.__setattr__(self, "report_directory", Path(self.report_directory))
        object.__setattr__(self, "dashboard_file", Path(self.dashboard_file))
        object.__setattr__(self, "research_snapshot_directory", Path(self.research_snapshot_directory))
        object.__setattr__(self, "alert_file", Path(self.alert_file))
        object.__setattr__(self, "assets", tuple(self.assets))
        if self.mode != "PAPER":
            raise PaperConfigurationError("Paper runtime mode must be PAPER.")
        if self.live_trading_enabled:
            raise PaperConfigurationError(
                "Live trading cannot be enabled by PaperRuntimeConfig."
            )
        if self.broker_submission_enabled:
            raise PaperConfigurationError(
                "Live broker submission cannot be enabled by PaperRuntimeConfig."
            )
        if tuple(self.assets) != tuple(PRODUCTION_ASSETS):
            raise PaperConfigurationError(
                "Paper deployment must use the canonical production asset order."
            )
        if self.benchmark not in self.assets:
            raise PaperConfigurationError(
                "Benchmark must belong to the configured universe."
            )
        if not self.market_period.strip():
            raise PaperConfigurationError("market_period cannot be empty.")
        if self.rebalance_interval_days <= 0:
            raise PaperConfigurationError("rebalance_interval_days must be positive.")
        if self.maximum_price_age_hours <= 0:
            raise PaperConfigurationError("maximum_price_age_hours must be positive.")
        if not math.isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise PaperConfigurationError("initial_cash must be positive.")
        if not math.isfinite(self.cash_buffer_fraction) or not 0.0 <= self.cash_buffer_fraction < 0.25:
            raise PaperConfigurationError("cash_buffer_fraction must be in [0, 0.25).")
        if not math.isfinite(self.commission_rate) or not 0.0 <= self.commission_rate <= 0.05:
            raise PaperConfigurationError("commission_rate must be in [0, 0.05].")
        if not math.isfinite(self.slippage_rate) or not 0.0 <= self.slippage_rate <= 0.10:
            raise PaperConfigurationError("slippage_rate must be in [0, 0.10].")
        if not self.timezone.strip():
            raise PaperConfigurationError("timezone cannot be empty.")
        smtp_values = (
            self.smtp_host,
            self.smtp_sender,
            self.smtp_recipient,
            self.smtp_username,
            self.smtp_password,
        )
        required_smtp_values = (self.smtp_host, self.smtp_sender, self.smtp_recipient)
        if any(smtp_values) and not all(required_smtp_values):
            raise PaperConfigurationError(
                "SMTP host, sender, and recipient must be configured together."
            )
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise PaperConfigurationError(
                "SMTP username and password must be configured together."
            )
        if self.smtp_port <= 0:
            raise PaperConfigurationError("SMTP_PORT must be positive.")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise PaperConfigurationError(
                f"Unknown timezone: {self.timezone!r}."
            ) from exc

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "PaperRuntimeConfig":
        """Read paper settings from environment without accepting live flags."""
        env = os.environ if environ is None else environ
        forbidden_live_flags = (
            "LIVE_TRADING_ENABLED",
            "BROKER_SUBMISSION_ENABLED",
        )
        for key in forbidden_live_flags:
            value = env.get(key, "false").strip().lower()
            if value not in {"", "0", "false", "no", "off"}:
                raise PaperConfigurationError(
                    f"{key} must be false in a paper deployment."
                )

        mode = env.get("TRADING_MODE", "PAPER").strip().upper()
        return cls(
            state_database=Path(
                env.get("PAPER_STATE_DATABASE", "var/paper-state.sqlite3")
            ),
            audit_log=Path(env.get("PAPER_AUDIT_LOG", "var/paper-audit.jsonl")),
            report_directory=Path(env.get("PAPER_REPORT_DIRECTORY", "var/paper-reports")),
            dashboard_file=Path(env.get("PAPER_DASHBOARD_FILE", "var/paper-dashboard.html")),
            research_snapshot_directory=Path(
                env.get("PAPER_RESEARCH_SNAPSHOT_DIRECTORY", "var/research-snapshots")
            ),
            alert_file=Path(env.get("PAPER_ALERT_FILE", "var/paper-alerts.jsonl")),
            market_period=env.get("MARKET_DATA_PERIOD", "15y"),
            rebalance_interval_days=_positive_int(
                "REBALANCE_INTERVAL_DAYS",
                env.get("REBALANCE_INTERVAL_DAYS", "21"),
            ),
            maximum_price_age_hours=_positive_int(
                "MAXIMUM_PRICE_AGE_HOURS",
                env.get("MAXIMUM_PRICE_AGE_HOURS", "72"),
            ),
            initial_cash=float(env.get("PAPER_INITIAL_CASH", "1000000")),
            cash_buffer_fraction=float(env.get("PAPER_CASH_BUFFER_FRACTION", "0.01")),
            commission_rate=float(env.get("PAPER_COMMISSION_RATE", "0.0005")),
            slippage_rate=float(env.get("PAPER_SLIPPAGE_RATE", "0.001")),
            smtp_host=env.get("PAPER_SMTP_HOST") or None,
            smtp_port=_positive_int("PAPER_SMTP_PORT", env.get("PAPER_SMTP_PORT", "587")),
            smtp_sender=env.get("PAPER_SMTP_SENDER") or None,
            smtp_recipient=env.get("PAPER_ALERT_RECIPIENT") or None,
            smtp_username=env.get("PAPER_SMTP_USERNAME") or None,
            smtp_password=env.get("PAPER_SMTP_PASSWORD") or None,
            smtp_use_tls=_boolean(
                "PAPER_SMTP_USE_TLS",
                env.get("PAPER_SMTP_USE_TLS", "true"),
            ),
            timezone=env.get("TRADING_TIMEZONE", "UTC"),
            benchmark=env.get("BENCHMARK", "SPY").strip().upper(),
            mode=mode,
        )
