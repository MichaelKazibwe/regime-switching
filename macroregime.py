from enum import Enum

# ============================================================
# MACRO REGIMES
# ============================================================


class Regime(Enum):

    EXPANSION = "expansion"

    SLOWDOWN = "slowdown"

    RECESSION = "recession"

    RECOVERY = "recovery"


class MacroRegimeModel:

    # ========================================================
    # CLASSIFICATION
    # ========================================================

    def classify(
        self,
        unemployment,
        yield_spread,
        inflation,
    ):
        """
        Classify the current macroeconomic regime.

        Inputs may be either:

        1. pandas Series containing historical observations, or
        2. scalar values representing the latest observations.

        When unemployment history is available, the change in
        unemployment is used to identify a slowdown.

        When only the latest unemployment observation is available,
        no unemployment trend can be inferred, so the model falls
        through to the remaining regime rules.
        """

        # ====================================================
        # YIELD CURVE / RECESSION
        # ====================================================

        yield_spread_value = (
            self._latest_value(
                yield_spread
            )
        )

        if yield_spread_value < 0.0:

            return Regime.RECESSION

        # ====================================================
        # UNEMPLOYMENT / SLOWDOWN
        # ====================================================

        unemployment_change = (
            self._latest_change(
                unemployment
            )
        )

        if (
            unemployment_change is not None
            and unemployment_change > 0.0
        ):

            return Regime.SLOWDOWN

        # ====================================================
        # INFLATION / RECOVERY
        # ====================================================

        inflation_value = (
            self._latest_value(
                inflation
            )
        )

        if inflation_value > 4.0:

            return Regime.RECOVERY

        # ====================================================
        # DEFAULT
        # ====================================================

        return Regime.EXPANSION

    # ========================================================
    # INTERNAL HELPERS
    # ========================================================

    @staticmethod
    def _latest_value(
        value,
    ):
        """
        Return the latest scalar observation.

        Supports pandas Series, numpy scalar-like objects,
        and ordinary Python numeric values.
        """

        if value is None:

            raise ValueError(
                "Macro variable cannot be None."
            )

        # pandas Series / DataFrame-like objects
        if hasattr(
            value,
            "iloc",
        ):

            if len(value) == 0:

                raise ValueError(
                    "Macro variable contains no observations."
                )

            value = value.iloc[-1]

        # numpy scalar / pandas scalar
        if hasattr(
            value,
            "item",
        ):

            try:

                value = value.item()

            except (
                ValueError,
                AttributeError,
            ):

                pass

        return float(
            value
        )

    # ========================================================

    @staticmethod
    def _latest_change(
        value,
    ):
        """
        Return the latest first difference.

        For historical pandas Series:

            latest_change = series.diff().iloc[-1]

        For a scalar input, there is no history from which to
        calculate a change, so None is returned.
        """

        if value is None:

            return None

        # Historical series
        if hasattr(
            value,
            "diff",
        ) and hasattr(
            value,
            "iloc",
        ):

            if len(value) < 2:

                return None

            change = (
                value
                .diff()
                .iloc[-1]
            )

            if hasattr(
                change,
                "item",
            ):

                try:

                    change = change.item()

                except (
                    ValueError,
                    AttributeError,
                ):

                    pass

            return float(
                change
            )

        # Scalar input: no history available
        return None


# ============================================================
# PORTFOLIO REGIME MAPPER
# ============================================================


class PortfolioRegimeMapper:

    @staticmethod
    def map_regime(
        macro_regime,
    ):

        if macro_regime in [

            Regime.EXPANSION,
            Regime.RECOVERY,

        ]:

            return "bull"

        if macro_regime == Regime.SLOWDOWN:

            return "neutral"

        return "crisis"