"""
======================================================================
PORTFOLIO RISK REPORT
======================================================================

R4.11
------
Production risk-report integration layer with locked R4 options-risk inputs.

Purpose
-------
This module assembles already-calculated portfolio analytics into one
canonical, machine-readable and human-readable risk report.

The report consumes outputs from the existing production components:

    PerformanceAnalytics
    TradeAnalytics
    DrawdownRiskEngine
    StressTailRiskEngine
    FactorStressRiskEngine
    VolatilityCorrelationStressEngine
    ATRPositionSizer
    PortfolioRiskGovernor
    PortfolioOptimizer
    PortfolioGreeksAggregator (R4.5)
    PutCallParityDiagnostics (R4.6)
    OptionsTailRiskEngine (R4.9)
    OptionsRiskGovernor (R4.10)

It does NOT replace those engines and does not silently recalculate
their authoritative analytics.

Design principles
-----------------
* One reporting responsibility.
* No competing risk calculations.
* Existing component outputs remain authoritative.
* Missing analytics are represented explicitly rather than guessed.
* Risk units and provenance are retained.
* The report is analytics-only.
* The Risk Governor remains the authority for portfolio governance.
* R4 options analytics are accepted as authoritative supplied results.
* The report does not recalculate valuation, Greeks, parity, tail risk,
  or governance decisions.
======================================================================
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from basecomponent import BaseObject

class PortfolioRiskReportError(ValueError):
    """Raised when portfolio risk-report inputs are invalid."""


@dataclass(frozen=True)
class RiskReportResult:
    """Immutable canonical portfolio risk report."""

    capital: dict[str, Any]
    return_metrics: dict[str, Any]
    risk_metrics: dict[str, Any]
    drawdown_metrics: dict[str, Any]
    risk_adjusted_metrics: dict[str, Any]
    trade_quality: dict[str, Any]
    position_risk: dict[str, Any]
    tail_risk: dict[str, Any]
    options_risk: dict[str, Any]
    risk_status: str
    status_reasons: tuple[str, ...]
    provenance: dict[str, Any]
    method: str


class PortfolioRiskReport(BaseObject):
    """
    Canonical portfolio risk-report assembler.

    The class is intentionally downstream of the risk engines. It
    assembles their outputs into the final report contract and does not
    become a second risk-calculation engine.
    """

    API_VERSION = "1.0.0"
    PHASE = "R4.11"
    COMPONENT = "PortfolioRiskReport"

    DEFAULT_NAV = 100_000.0

    PUBLIC_METHODS = (
        "build",
        "render",
        "summary",
        "metadata",
        "health_check",
        "validate",
        "to_dict",
        "save_json",
    )

    _SECTION_NAMES = (
        "capital",
        "return_metrics",
        "risk_metrics",
        "drawdown_metrics",
        "risk_adjusted_metrics",
        "trade_quality",
        "position_risk",
        "tail_risk",
        "options_risk",
    )

    def __init__(
        self,
        nav: float = DEFAULT_NAV,
        periods_per_year: int = 252,
        frequency: str = "daily",
    ) -> None:
        super().__init__()

        self.nav = self._validate_positive(
            nav,
            "nav",
        )
        self.periods_per_year = self._validate_positive_int(
            periods_per_year,
            "periods_per_year",
        )

        if not isinstance(frequency, str) or not frequency.strip():
            raise PortfolioRiskReportError(
                "frequency must be a non-empty string."
            )

        self.frequency = frequency.strip().lower()

        self.report_count = 0
        self.last_result: RiskReportResult | None = None

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_positive(
        value: Any,
        name: str,
    ) -> float:
        if isinstance(value, bool):
            raise PortfolioRiskReportError(
                f"{name} must be a positive finite number."
            )

        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise PortfolioRiskReportError(
                f"{name} must be a positive finite number."
            ) from exc

        if not np.isfinite(result) or result <= 0.0:
            raise PortfolioRiskReportError(
                f"{name} must be a positive finite number."
            )

        return result

    @staticmethod
    def _validate_positive_int(
        value: Any,
        name: str,
    ) -> int:
        if isinstance(value, bool):
            raise PortfolioRiskReportError(
                f"{name} must be a positive integer."
            )

        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise PortfolioRiskReportError(
                f"{name} must be a positive integer."
            ) from exc

        if result <= 0:
            raise PortfolioRiskReportError(
                f"{name} must be a positive integer."
            )

        return result

    @staticmethod
    def _mapping(
        value: Mapping[str, Any] | None,
        name: str,
    ) -> dict[str, Any]:
        if value is None:
            return {}

        if not isinstance(value, Mapping):
            raise PortfolioRiskReportError(
                f"{name} must be a mapping."
            )

        return dict(value)

    @staticmethod
    def _finite_optional(
        value: Any,
        name: str,
    ) -> float | None:
        if value is None:
            return None

        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise PortfolioRiskReportError(
                f"{name} must be numeric or None."
            ) from exc

        if not np.isfinite(result):
            raise PortfolioRiskReportError(
                f"{name} must be finite or None."
            )

        return result

    @staticmethod
    def _clean_value(value: Any) -> Any:
        """Convert common NumPy/scalar values to JSON-safe values."""
        if isinstance(value, np.generic):
            value = value.item()

        if isinstance(value, Mapping):
            return {
                str(key): PortfolioRiskReport._clean_value(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [
                PortfolioRiskReport._clean_value(item)
                for item in value
            ]

        if isinstance(value, float):
            if math.isfinite(value):
                return value
            return None

        return value

    @staticmethod
    def _first(
        mappings: Sequence[Mapping[str, Any]],
        keys: Sequence[str],
        default: Any = None,
    ) -> Any:
        for mapping in mappings:
            for key in keys:
                if key in mapping and mapping[key] is not None:
                    return mapping[key]
        return default

    @staticmethod
    def _result_mapping(
        value: Any,
        name: str,
        required_fields: Sequence[str],
    ) -> dict[str, Any]:
        """
        Normalize one authoritative upstream result.

        R4 result objects are immutable dataclasses, but mappings and
        compatible result objects are also accepted for integration
        compatibility. No analytics are recalculated here.
        """
        if value is None:
            return {}

        if isinstance(value, Mapping):
            payload = dict(value)
        elif hasattr(value, "to_dict") and callable(value.to_dict):
            payload = value.to_dict()
            if not isinstance(payload, Mapping):
                raise PortfolioRiskReportError(
                    f"{name}.to_dict() must return a mapping."
                )
            payload = dict(payload)
        else:
            try:
                payload = asdict(value)
            except TypeError as exc:
                raise PortfolioRiskReportError(
                    f"{name} must be a mapping, dataclass result, "
                    "or compatible result object."
                ) from exc

        missing = [
            field
            for field in required_fields
            if field not in payload
        ]
        if missing:
            raise PortfolioRiskReportError(
                f"{name} is missing required fields: "
                + ", ".join(missing)
            )

        return payload

    @staticmethod
    def _optional_result_mapping(
        value: Any,
        name: str,
        required_fields: Sequence[str],
    ) -> dict[str, Any]:
        """Normalize an optional authoritative R4 result."""
        return PortfolioRiskReport._result_mapping(
            value,
            name,
            required_fields,
        )

    # ==================================================================
    # EXPOSURE
    # ==================================================================

    def _capital_section(
        self,
        nav: float,
        weights: Mapping[str, float] | None,
        cash: float | None,
        financing: float | None,
        capital: Mapping[str, Any],
    ) -> dict[str, Any]:
        supplied = dict(capital)

        if weights is not None:
            if not isinstance(weights, Mapping):
                raise PortfolioRiskReportError(
                    "weights must be a mapping when supplied."
                )

            values = []
            for asset, value in weights.items():
                try:
                    numeric = float(value)
                except (TypeError, ValueError) as exc:
                    raise PortfolioRiskReportError(
                        f"Weight for {asset!r} must be numeric."
                    ) from exc

                if not np.isfinite(numeric):
                    raise PortfolioRiskReportError(
                        f"Weight for {asset!r} must be finite."
                    )

                values.append(numeric)

            gross = float(np.sum(np.abs(values)))
            net = float(np.sum(values))
        else:
            gross = self._finite_optional(
                supplied.get("gross_exposure"),
                "gross_exposure",
            )
            net = self._finite_optional(
                supplied.get("net_exposure"),
                "net_exposure",
            )

        cash_weight = (
            self._finite_optional(cash, "cash")
            if cash is not None
            else self._finite_optional(
                supplied.get("cash"),
                "cash",
            )
        )

        financing_weight = (
            self._finite_optional(financing, "financing")
            if financing is not None
            else self._finite_optional(
                supplied.get("financing"),
                "financing",
            )
        )

        if gross is None:
            gross = 0.0
        if net is None:
            net = 0.0
        if cash_weight is None:
            cash_weight = max(
                0.0,
                1.0 - gross,
            )

        result = {
            "NAV": float(nav),
            "gross_exposure": float(gross),
            "net_exposure": float(net),
            "cash": float(cash_weight),
            "financing": (
                0.0
                if financing_weight is None
                else float(financing_weight)
            ),
        }

        for key, value in supplied.items():
            if key not in result:
                result[key] = value

        return result

    # ==================================================================
    # STATUS
    # ==================================================================

    def _risk_status(
        self,
        risk_governance: Mapping[str, Any] | None,
        risk_metrics: Mapping[str, Any],
        tail_risk: Mapping[str, Any],
        drawdown_metrics: Mapping[str, Any],
        status_override: str | None,
    ) -> tuple[str, tuple[str, ...]]:
        if status_override is not None:
            status = str(status_override).upper().strip()
            if status not in {"GREEN", "AMBER", "RED"}:
                raise PortfolioRiskReportError(
                    "status_override must be GREEN, AMBER, or RED."
                )
            return status, ("Status supplied explicitly.",)

        governance = (
            {}
            if risk_governance is None
            else dict(risk_governance)
        )

        action = str(
            governance.get("action", "")
        ).upper()

        if action == "REJECT":
            return "RED", (
                "Risk Governor rejected the candidate portfolio.",
            )

        if action == "REDUCE":
            reasons = [
                "Risk Governor reduced portfolio exposure.",
            ]

            breaches = governance.get("breaches")
            if isinstance(breaches, (list, tuple)) and breaches:
                reasons.append(
                    "Governance breaches: "
                    + ", ".join(str(item) for item in breaches)
                )

            return "AMBER", tuple(reasons)

        reasons: list[str] = []

        current_dd = self._first(
            [drawdown_metrics],
            (
                "current_drawdown",
                "current_drawdown_pct",
            ),
        )
        if current_dd is not None:
            try:
                if abs(float(current_dd)) >= 0.20:
                    reasons.append(
                        "Current drawdown is at or above 20%."
                    )
            except (TypeError, ValueError):
                pass

        ruin = self._first(
            [tail_risk],
            (
                "risk_of_ruin",
                "ruin_probability",
            ),
        )
        if ruin is not None:
            try:
                if float(ruin) >= 0.10:
                    reasons.append(
                        "Estimated finite-horizon risk of ruin is "
                        "at or above 10%."
                    )
            except (TypeError, ValueError):
                pass

        if reasons:
            return "AMBER", tuple(reasons)

        if governance.get("approved") is False:
            return "RED", (
                "Portfolio governance reports the candidate as not approved.",
            )

        return "GREEN", (
            "No supplied governance or report-level escalation condition "
            "requires AMBER or RED status.",
        )

    # ==================================================================
    # BUILD
    # ==================================================================

    def build(
        self,
        *,
        nav: float | None = None,
        weights: Mapping[str, float] | None = None,
        cash: float | None = None,
        financing: float | None = None,
        performance: Mapping[str, Any] | None = None,
        risk: Mapping[str, Any] | None = None,
        drawdown: Mapping[str, Any] | None = None,
        risk_adjusted: Mapping[str, Any] | None = None,
        trade_quality: Mapping[str, Any] | None = None,
        position_risk: Mapping[str, Any] | None = None,
        tail_risk: Mapping[str, Any] | None = None,
        options_risk: Mapping[str, Any] | None = None,
        portfolio_greeks: Any | None = None,
        parity_diagnostics: Any | None = None,
        options_tail_risk: Any | None = None,
        options_governance: Any | None = None,
        risk_governance: Mapping[str, Any] | None = None,
        capital: Mapping[str, Any] | None = None,
        status_override: str | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> RiskReportResult:
        """
        Assemble the canonical portfolio risk report.

        Supplied analytics remain authoritative. Missing values are
        represented as None/explicit defaults rather than inferred from
        unrelated data.
        """
        report_nav = (
            self.nav
            if nav is None
            else self._validate_positive(nav, "nav")
        )

        performance_map = self._mapping(
            performance,
            "performance",
        )
        risk_map = self._mapping(
            risk,
            "risk",
        )
        drawdown_map = self._mapping(
            drawdown,
            "drawdown",
        )
        risk_adjusted_map = self._mapping(
            risk_adjusted,
            "risk_adjusted",
        )
        trade_map = self._mapping(
            trade_quality,
            "trade_quality",
        )
        position_map = self._mapping(
            position_risk,
            "position_risk",
        )
        tail_map = self._mapping(
            tail_risk,
            "tail_risk",
        )
        options_map = self._mapping(
            options_risk,
            "options_risk",
        )

        greeks_map = self._optional_result_mapping(
            portfolio_greeks,
            "portfolio_greeks",
            (
                "net_delta",
                "net_gamma",
                "net_vega",
            ),
        )

        parity_map = self._optional_result_mapping(
            parity_diagnostics,
            "parity_diagnostics",
            (
                "parity_deviation",
            ),
        )

        options_tail_map = self._optional_result_mapping(
            options_tail_risk,
            "options_tail_risk",
            (
                "aggregate_tail_loss",
                "aggregate_tail_loss_pct",
                "tail_loss_source",
            ),
        )

        options_governance_map = self._optional_result_mapping(
            options_governance,
            "options_governance",
            (
                "action",
                "approved",
            ),
        )

        governance_map = self._mapping(
            risk_governance,
            "risk_governance",
        )
        capital_map = self._mapping(
            capital,
            "capital",
        )
        provenance_map = self._mapping(
            provenance,
            "provenance",
        )

        capital_section = self._capital_section(
            report_nav,
            weights,
            cash,
            financing,
            capital_map,
        )

        # Preserve the canonical report labels while accepting the
        # existing internal naming conventions.
        return_section = {
            "annual_return": self._first(
                [performance_map],
                ("annual_return", "return"),
            ),
            "CAGR": self._first(
                [performance_map],
                ("CAGR", "cagr"),
            ),
            "annual_return_estimate": self._first(
                [performance_map],
                (
                    "annual_return_estimate",
                    "annualized_return_estimate",
                ),
            ),
        }

        risk_section = {
            "annual_volatility": self._first(
                [risk_map, performance_map],
                ("annual_volatility", "volatility"),
            ),
            "VaR_95": self._first(
                [risk_map, tail_map],
                ("VaR_95", "var_95", "var95", "var"),
            ),
            "CVaR_95": self._first(
                [risk_map, tail_map],
                ("CVaR_95", "cvar_95", "cvar95", "cvar"),
            ),
            "VaR_99": self._first(
                [risk_map, tail_map],
                ("VaR_99", "var_99", "var99"),
            ),
            "CVaR_99": self._first(
                [risk_map, tail_map],
                ("CVaR_99", "cvar_99", "cvar99"),
            ),
        }

        drawdown_section = {
            "current_drawdown": self._first(
                [drawdown_map],
                ("current_drawdown",),
            ),
            "maximum_drawdown": self._first(
                [drawdown_map, performance_map],
                ("maximum_drawdown", "max_drawdown"),
            ),
            "drawdown_duration": self._first(
                [drawdown_map],
                (
                    "drawdown_duration",
                    "current_drawdown_duration",
                ),
            ),
            "recovery_time": self._first(
                [drawdown_map],
                ("recovery_time",),
            ),
            "time_under_water": self._first(
                [drawdown_map],
                ("time_under_water",),
            ),
        }

        risk_adjusted_section = {
            "sharpe": self._first(
                [risk_adjusted_map, performance_map],
                ("sharpe", "sharpe_ratio"),
            ),
            "sortino": self._first(
                [risk_adjusted_map, performance_map],
                ("sortino", "sortino_ratio"),
            ),
            "calmar": self._first(
                [risk_adjusted_map, performance_map],
                ("calmar", "calmar_ratio"),
            ),
            "information_ratio": self._first(
                [risk_adjusted_map, performance_map],
                ("information_ratio", "information_ratio_value"),
            ),
            "alpha": self._first(
                [risk_adjusted_map, performance_map],
                ("alpha",),
            ),
            "beta": self._first(
                [risk_adjusted_map, performance_map],
                ("beta",),
            ),
        }

        trade_section = {
            "trades": self._first(
                [trade_map],
                ("trades", "outcome_count", "trade_count"),
            ),
            "win_rate": self._first(
                [trade_map],
                ("win_rate",),
            ),
            "average_winner": self._first(
                [trade_map],
                ("average_winner", "average_win"),
            ),
            "average_loser": self._first(
                [trade_map],
                ("average_loser", "average_loss"),
            ),
            "reward_risk": self._first(
                [trade_map],
                ("reward_risk", "reward_risk_ratio"),
            ),
            "expectancy": self._first(
                [trade_map],
                ("expectancy", "trade_expectancy"),
            ),
            "profit_factor": self._first(
                [trade_map],
                ("profit_factor",),
            ),
            "break_even_win_rate": self._first(
                [trade_map],
                ("break_even_win_rate",),
            ),
        }

        position_section = {
            "kelly_fraction": self._first(
                [position_map, trade_map],
                ("kelly_fraction", "kelly_criterion"),
            ),
            "fractional_kelly": self._first(
                [position_map, trade_map],
                ("fractional_kelly",),
            ),
            "atr_risk_per_position": self._first(
                [position_map],
                (
                    "atr_risk_per_position",
                    "atr_risk",
                    "ATR Risk / Position",
                ),
            ),
            "largest_risk_contributor": self._first(
                [position_map],
                ("largest_risk_contributor",),
            ),
            "largest_factor_exposure": self._first(
                [position_map, tail_map],
                ("largest_factor_exposure",),
            ),
        }

        tail_section = {
            "risk_of_ruin": self._first(
                [tail_map],
                ("risk_of_ruin", "ruin_probability"),
            ),
            "P_DD_gt_10": self._first(
                [tail_map],
                (
                    "P(DD > 10%)",
                    "prob_dd_10pct",
                    "p_dd_10",
                ),
            ),
            "P_DD_gt_20": self._first(
                [tail_map],
                (
                    "P(DD > 20%)",
                    "prob_dd_20pct",
                    "p_dd_20",
                ),
            ),
            "P_DD_gt_30": self._first(
                [tail_map],
                (
                    "P(DD > 30%)",
                    "prob_dd_30pct",
                    "p_dd_30",
                ),
            ),
            "P_DD_gt_50": self._first(
                [tail_map],
                (
                    "P(DD > 50%)",
                    "prob_dd_50pct",
                    "p_dd_50",
                ),
            ),
        }

        # R4.11 authority order:
        #   R4.5 PortfolioGreeksResult
        #   R4.6 PutCallParityResult
        #   legacy options_risk mapping
        #
        # The legacy mapping remains supported for backward compatibility.
        # R4 typed results take precedence when supplied.
        options_section = {
            "net_delta": self._first(
                [greeks_map, options_map],
                ("net_delta", "delta"),
            ),
            "gamma": self._first(
                [greeks_map, options_map],
                ("net_gamma", "gamma"),
            ),
            "vega": self._first(
                [greeks_map, options_map],
                ("net_vega", "vega"),
            ),
            "put_call_parity_deviation": self._first(
                [parity_map, options_map],
                (
                    "parity_deviation",
                    "put_call_parity_deviation",
                    "put_call_parity",
                ),
            ),
            # Zomma is deliberately not inferred. R4.4 does not currently
            # publish a Zomma field, so the report preserves the supplied
            # value or returns None.
            "zomma": self._first(
                [options_map],
                ("zomma",),
            ),
            # Structured R4.9 tail-risk diagnostics are retained in the
            # machine-readable report but are not substituted for the
            # portfolio's historical VaR/CVaR/tail-risk section.
            "options_tail_loss": self._first(
                [options_tail_map],
                ("aggregate_tail_loss",),
            ),
            "options_tail_loss_pct": self._first(
                [options_tail_map],
                ("aggregate_tail_loss_pct",),
            ),
            "options_tail_loss_source": self._first(
                [options_tail_map],
                ("tail_loss_source",),
            ),
            "options_tail_worst_scenario": self._first(
                [options_tail_map],
                ("worst_scenario_name",),
            ),
            "options_tail_worst_scenario_loss": self._first(
                [options_tail_map],
                ("worst_scenario_loss",),
            ),
            # R4.10 governance is preserved as supplied governance
            # information. The report never changes the decision.
            "options_governance_action": self._first(
                [options_governance_map],
                ("action",),
            ),
            "options_governance_approved": self._first(
                [options_governance_map],
                ("approved",),
            ),
            "options_governance_scale": self._first(
                [options_governance_map],
                ("scale", "governed_scale"),
            ),
            "options_governance_reasons": self._first(
                [options_governance_map],
                ("reasons",),
            ),
        }

        status, reasons = self._risk_status(
            governance_map,
            risk_section,
            tail_section,
            drawdown_section,
            status_override,
        )

        source_provenance = {
            "performance": (
                provenance_map.get(
                    "performance",
                    "PerformanceAnalytics",
                )
            ),
            "tail_risk": (
                provenance_map.get(
                    "tail_risk",
                    "StressTailRiskEngine / TailAggregationEngine",
                )
            ),
            "drawdown": (
                provenance_map.get(
                    "drawdown",
                    "DrawdownRiskEngine",
                )
            ),
            "position_risk": (
                provenance_map.get(
                    "position_risk",
                    "ATRPositionSizer / TradeAnalytics",
                )
            ),
            "risk_governance": (
                provenance_map.get(
                    "risk_governance",
                    "PortfolioRiskGovernor",
                )
            ),
            "options_risk": (
                provenance_map.get(
                    "options_risk",
                    "R4.5 PortfolioGreeksAggregator / "
                    "R4.6 PutCallParityDiagnostics / "
                    "R4.9 OptionsTailRiskEngine / "
                    "R4.10 OptionsRiskGovernor",
                )
            ),
            "options_greeks": (
                "R4.5 PortfolioGreeksAggregator"
                if greeks_map
                else None
            ),
            "options_parity": (
                "R4.6 PutCallParityDiagnostics"
                if parity_map
                else None
            ),
            "options_tail_risk": (
                "R4.9 OptionsTailRiskEngine"
                if options_tail_map
                else None
            ),
            "options_governance": (
                "R4.10 OptionsRiskGovernor"
                if options_governance_map
                else None
            ),
        }

        result = RiskReportResult(
            capital=self._clean_value(capital_section),
            return_metrics=self._clean_value(return_section),
            risk_metrics=self._clean_value(risk_section),
            drawdown_metrics=self._clean_value(drawdown_section),
            risk_adjusted_metrics=self._clean_value(
                risk_adjusted_section
            ),
            trade_quality=self._clean_value(trade_section),
            position_risk=self._clean_value(position_section),
            tail_risk=self._clean_value(tail_section),
            options_risk=self._clean_value(options_section),
            risk_status=status,
            status_reasons=tuple(reasons),
            provenance=self._clean_value(source_provenance),
            method="assembled_production_risk_report",
        )

        self.report_count += 1
        self.last_result = result

        return result

    # ==================================================================
    # RENDER
    # ==================================================================

    @staticmethod
    def _fmt_percent(value: Any) -> str:
        if value is None:
            return "N/A"

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "N/A"

        if not np.isfinite(numeric):
            return "N/A"

        return f"{numeric * 100:.2f}%"

    @staticmethod
    def _fmt_number(value: Any, decimals: int = 2) -> str:
        if value is None:
            return "N/A"

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "N/A"

        if not np.isfinite(numeric):
            if numeric > 0:
                return "∞"
            return "N/A"

        return f"{numeric:.{decimals}f}"

    @staticmethod
    def _fmt_days(value: Any) -> str:
        if value is None:
            return "N/A"

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "N/A"

        if not np.isfinite(numeric):
            return "N/A"

        return f"{int(round(numeric))} days"

    def render(
        self,
        result: RiskReportResult | None = None,
    ) -> str:
        """Render the canonical report as a text report."""
        selected = result or self.last_result

        if selected is None:
            raise PortfolioRiskReportError(
                "No risk report has been built."
            )

        capital = selected.capital
        returns = selected.return_metrics
        risk = selected.risk_metrics
        drawdown = selected.drawdown_metrics
        adjusted = selected.risk_adjusted_metrics
        trades = selected.trade_quality
        position = selected.position_risk
        tail = selected.tail_risk
        options = selected.options_risk

        lines = [
            "=========================================================",
            "              PORTFOLIO RISK REPORT",
            "=========================================================",
            "CAPITAL",
            "---------------------------------------------------------",
            f"NAV                         €{self._fmt_number(capital.get('NAV'), 2)}",
            f"Gross Exposure              {self._fmt_percent(capital.get('gross_exposure'))}",
            f"Net Exposure                {self._fmt_percent(capital.get('net_exposure'))}",
            f"Cash                        {self._fmt_percent(capital.get('cash'))}",
            "RETURN",
            "---------------------------------------------------------",
            f"Annual Return               {self._fmt_percent(returns.get('annual_return'))}",
            f"CAGR                        {self._fmt_percent(returns.get('CAGR'))}",
            f"Annual Return Estimate      {self._fmt_percent(returns.get('annual_return_estimate'))}",
            "RISK",
            "---------------------------------------------------------",
            f"Annual Volatility           {self._fmt_percent(risk.get('annual_volatility'))}",
            f"VaR 95%                     {self._fmt_percent(risk.get('VaR_95'))}",
            f"CVaR 95%                    {self._fmt_percent(risk.get('CVaR_95'))}",
            f"VaR 99%                     {self._fmt_percent(risk.get('VaR_99'))}",
            f"CVaR 99%                    {self._fmt_percent(risk.get('CVaR_99'))}",
            "DRAWDOWN",
            "---------------------------------------------------------",
            f"Current Drawdown            {self._fmt_percent(drawdown.get('current_drawdown'))}",
            f"Maximum Drawdown            {self._fmt_percent(drawdown.get('maximum_drawdown'))}",
            f"Drawdown Duration           {self._fmt_days(drawdown.get('drawdown_duration'))}",
            f"Recovery Time               {self._fmt_days(drawdown.get('recovery_time'))}",
            f"Time Under Water            {self._fmt_days(drawdown.get('time_under_water'))}",
            "RISK-ADJUSTED RETURN",
            "---------------------------------------------------------",
            f"Sharpe                      {self._fmt_number(adjusted.get('sharpe'))}",
            f"Sortino                     {self._fmt_number(adjusted.get('sortino'))}",
            f"Calmar                      {self._fmt_number(adjusted.get('calmar'))}",
            f"Information Ratio           {self._fmt_number(adjusted.get('information_ratio'))}",
            f"Alpha                       {self._fmt_percent(adjusted.get('alpha'))}",
            f"Beta                        {self._fmt_number(adjusted.get('beta'))}",
            "TRADE QUALITY",
            "---------------------------------------------------------",
            f"Trades                      {self._fmt_number(trades.get('trades'), 0)}",
            f"Win Rate                    {self._fmt_percent(trades.get('win_rate'))}",
            f"Average Winner              {self._fmt_number(trades.get('average_winner'))}",
            f"Average Loser               {self._fmt_number(trades.get('average_loser'))}",
            f"Reward/Risk                 {self._fmt_number(trades.get('reward_risk'))}",
            f"Expectancy                  {self._fmt_number(trades.get('expectancy'))}",
            f"Profit Factor               {self._fmt_number(trades.get('profit_factor'))}",
            f"Break-even Win Rate         {self._fmt_percent(trades.get('break_even_win_rate'))}",
            "POSITION RISK",
            "---------------------------------------------------------",
            f"Kelly Fraction              {self._fmt_percent(position.get('kelly_fraction'))}",
            f"Fractional Kelly            {self._fmt_percent(position.get('fractional_kelly'))}",
            f"ATR Risk / Position         {self._fmt_percent(position.get('atr_risk_per_position'))}",
            f"Largest Risk Contributor    {position.get('largest_risk_contributor') or 'N/A'}",
            f"Largest Factor Exposure     {position.get('largest_factor_exposure') or 'N/A'}",
            "TAIL RISK",
            "---------------------------------------------------------",
            f"Risk of Ruin                {self._fmt_percent(tail.get('risk_of_ruin'))}",
            f"P(DD > 10%)                 {self._fmt_percent(tail.get('P_DD_gt_10'))}",
            f"P(DD > 20%)                 {self._fmt_percent(tail.get('P_DD_gt_20'))}",
            f"P(DD > 30%)                 {self._fmt_percent(tail.get('P_DD_gt_30'))}",
            f"P(DD > 50%)                 {self._fmt_percent(tail.get('P_DD_gt_50'))}",
            "OPTIONS RISK",
            "---------------------------------------------------------",
            f"Net Delta                   {self._fmt_number(options.get('net_delta'))}",
            f"Gamma                       {self._fmt_number(options.get('gamma'))}",
            f"Vega                        {self._fmt_number(options.get('vega'))}",
            f"Put/Call Parity Deviation  {self._fmt_number(options.get('put_call_parity_deviation'))}",
            f"Zomma                       {self._fmt_number(options.get('zomma'))}",
            "=========================================================",
            f"                  RISK STATUS: {selected.risk_status}",
            "=========================================================",
        ]

        return "\n".join(lines)

    # ==================================================================
    # SUMMARY / SERIALIZATION
    # ==================================================================

    def summary(
        self,
        result: RiskReportResult | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-safe structured risk report."""
        selected = result or self.last_result

        if selected is None:
            raise PortfolioRiskReportError(
                "No risk report has been built."
            )

        return self._clean_value(asdict(selected))

    def to_dict(self) -> dict[str, Any]:
        """Return the latest report as a dictionary."""
        return self.summary()

    def save_json(
        self,
        path: str,
        result: RiskReportResult | None = None,
    ) -> None:
        """Persist a risk report to JSON."""
        with open(
            path,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                self.summary(result),
                handle,
                indent=2,
                default=str,
            )

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """Return report metadata and unit/provenance definitions."""
        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "frequency": self.frequency,
            "periods_per_year": self.periods_per_year,
            "report_method": "assembled_production_risk_report",
            "analytics_only": True,
            "governance": False,
            "execution": False,
            "missing_value_policy": (
                "Missing analytics are represented as N/A/None; "
                "the report does not infer them."
            ),
            "annualization_policy": (
                "Annualized metrics must be supplied by their "
                "authoritative upstream analytics engine."
            ),
            "tail_loss_policy": (
                "VaR/CVaR and tail-loss values are consumed from "
                "StressTailRiskEngine/TailAggregationEngine."
            ),
            "drawdown_policy": (
                "Drawdown and recovery values are consumed from "
                "DrawdownRiskEngine."
            ),
            "options_policy": (
                "R4.5 Greeks, R4.6 parity diagnostics, R4.9 options "
                "tail-risk, and R4.10 options-governance results are "
                "consumed as authoritative supplied analytics. The "
                "report does not recalculate them. Legacy options_risk "
                "mapping input remains supported for compatibility."
            ),
            "options_authority_policy": (
                "When both typed R4 results and legacy options_risk "
                "mapping values are supplied, typed R4 results take "
                "precedence for the metrics they publish."
            ),
            "zomma_policy": (
                "Zomma is not inferred. It remains None unless supplied "
                "by an authoritative upstream analytics source."
            ),
            "risk_status_policy": (
                "Risk status is a reporting classification and does not "
                "replace PortfolioRiskGovernor."
            ),
        }

    # ==================================================================
    # VALIDATION / HEALTH
    # ==================================================================

    def validate(self) -> dict[str, Any]:
        """Validate report-engine configuration."""
        errors: list[str] = []

        if not np.isfinite(self.nav) or self.nav <= 0.0:
            errors.append("nav must be positive and finite.")

        if (
            not isinstance(self.periods_per_year, int)
            or isinstance(self.periods_per_year, bool)
            or self.periods_per_year <= 0
        ):
            errors.append(
                "periods_per_year must be a positive integer."
            )

        if not isinstance(self.frequency, str) or not self.frequency:
            errors.append(
                "frequency must be a non-empty string."
            )

        return {
            "valid": not errors,
            "errors": errors,
        }

    def health_check(self) -> dict[str, Any]:
        """Return report-engine health status."""
        validation = self.validate()

        return {
            "healthy": validation["valid"],
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "report_count": self.report_count,
            "has_result": self.last_result is not None,
            "errors": validation["errors"],
        }


# ======================================================================
# SELF TEST
# ======================================================================


def test_portfolio_risk_report() -> None:
    """Deterministic R3E.8 report tests."""

    engine = PortfolioRiskReport(
        nav=100_000.0,
        periods_per_year=252,
        frequency="daily",
    )

    result = engine.build(
        weights={
            "SPY": 0.60,
            "TLT": 0.40,
        },
        performance={
            "annual_return": 0.12,
            "CAGR": 0.11,
            "annual_return_estimate": 0.13,
            "annual_volatility": 0.15,
        },
        risk={
            "VaR_95": 0.025,
            "CVaR_95": 0.035,
            "VaR_99": 0.045,
            "CVaR_99": 0.060,
        },
        drawdown={
            "current_drawdown": -0.04,
            "maximum_drawdown": -0.12,
            "drawdown_duration": 18,
            "recovery_time": 30,
            "time_under_water": 18,
        },
        risk_adjusted={
            "sharpe": 0.80,
            "sortino": 1.10,
            "calmar": 0.92,
            "information_ratio": 0.50,
            "alpha": 0.02,
            "beta": 0.85,
        },
        trade_quality={
            "trades": 100,
            "win_rate": 0.55,
            "average_winner": 1.8,
            "average_loser": -1.0,
            "reward_risk": 1.8,
            "expectancy": 0.54,
            "profit_factor": 2.2,
            "break_even_win_rate": 0.3571428571,
        },
        position_risk={
            "kelly_fraction": 0.20,
            "fractional_kelly": 0.05,
            "atr_risk_per_position": 0.005,
            "largest_risk_contributor": "SPY",
            "largest_factor_exposure": "Equity Beta",
        },
        tail_risk={
            "risk_of_ruin": 0.01,
            "P(DD > 10%)": 0.15,
            "P(DD > 20%)": 0.04,
            "P(DD > 30%)": 0.01,
            "P(DD > 50%)": 0.001,
        },
        options_risk={
            "net_delta": 0.0,
            "gamma": 0.0,
            "vega": 0.0,
            "put_call_parity_deviation": 0.0,
            "zomma": 0.0,
        },
        risk_governance={
            "action": "PASS",
            "approved": True,
        },
    )

    assert np.isclose(
        result.capital["NAV"],
        100_000.0,
    )

    assert np.isclose(
        result.capital["gross_exposure"],
        1.0,
    )

    assert np.isclose(
        result.capital["net_exposure"],
        1.0,
    )

    assert result.risk_status == "GREEN"

    rendered = engine.render(result)

    assert "PORTFOLIO RISK REPORT" in rendered
    assert "VaR 95%" in rendered
    assert "CVaR 95%" in rendered
    assert "Risk of Ruin" in rendered
    assert "RISK STATUS: GREEN" in rendered

    payload = engine.to_dict()

    assert payload["risk_metrics"]["VaR_95"] == 0.025
    assert payload["tail_risk"]["P_DD_gt_50"] == 0.001

    health = engine.health_check()

    assert health["healthy"] is True

    print(
        "PortfolioRiskReport R3E.8 regression tests passed."
    )


# ======================================================================
# R4.11 SELF-TEST
# ======================================================================


def test_portfolio_risk_report_r4_11_options_integration() -> None:
    """Deterministic R4.11 options-report integration tests."""
    engine = PortfolioRiskReport(
        nav=100_000.0,
        periods_per_year=252,
        frequency="daily",
    )

    result = engine.build(
        weights={"SPY": 0.60, "TLT": 0.40},
        risk={"VaR_95": 0.025, "CVaR_95": 0.035},
        tail_risk={"risk_of_ruin": 0.01},
        options_risk={
            "net_delta": 999.0,
            "gamma": 999.0,
            "vega": 999.0,
            "put_call_parity_deviation": 999.0,
            "zomma": 0.125,
        },
        portfolio_greeks={
            "net_delta": 12.5,
            "net_gamma": -0.75,
            "net_vega": 44.0,
        },
        parity_diagnostics={
            "parity_deviation": 0.0025,
        },
        options_tail_risk={
            "aggregate_tail_loss": 8500.0,
            "aggregate_tail_loss_pct": 0.085,
            "tail_loss_source": "options_stress_max_scenario_envelope",
            "worst_scenario_name": "combined_spot_volatility",
            "worst_scenario_loss": 8500.0,
        },
        options_governance={
            "action": "REDUCE",
            "approved": True,
            "scale": 0.50,
            "reasons": ("Options tail-loss limit breached.",),
        },
        risk_governance={"action": "PASS", "approved": True},
    )

    assert np.isclose(result.options_risk["net_delta"], 12.5)
    assert np.isclose(result.options_risk["gamma"], -0.75)
    assert np.isclose(result.options_risk["vega"], 44.0)
    assert np.isclose(
        result.options_risk["put_call_parity_deviation"],
        0.0025,
    )
    assert np.isclose(result.options_risk["zomma"], 0.125)
    assert np.isclose(
        result.options_risk["options_tail_loss"],
        8500.0,
    )
    assert np.isclose(
        result.options_risk["options_tail_loss_pct"],
        0.085,
    )
    assert result.options_risk["options_tail_loss_source"] == (
        "options_stress_max_scenario_envelope"
    )
    assert result.options_risk["options_governance_action"] == "REDUCE"
    assert result.options_risk["options_governance_approved"] is True
    assert np.isclose(result.options_risk["options_governance_scale"], 0.50)

    payload = engine.to_dict()
    assert payload["options_risk"]["net_delta"] == 12.5
    assert payload["provenance"]["options_greeks"] == (
        "R4.5 PortfolioGreeksAggregator"
    )
    assert payload["provenance"]["options_parity"] == (
        "R4.6 PutCallParityDiagnostics"
    )
    assert payload["provenance"]["options_tail_risk"] == (
        "R4.9 OptionsTailRiskEngine"
    )
    assert payload["provenance"]["options_governance"] == (
        "R4.10 OptionsRiskGovernor"
    )

    rendered = engine.render(result)
    assert "Net Delta" in rendered
    assert "Gamma" in rendered
    assert "Vega" in rendered
    assert "Put/Call Parity Deviation" in rendered
    assert "Zomma" in rendered

    print("PortfolioRiskReport R4.11 options integration tests passed.")


if __name__ == "__main__":
    test_portfolio_risk_report()
    test_portfolio_risk_report_r4_11_options_integration()
