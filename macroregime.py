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

    def classify(
        self,
        unemployment,
        yield_spread,
        inflation
    ):

        if yield_spread < 0:

            return Regime.RECESSION

        if unemployment.diff().iloc[-1] > 0:

            return Regime.SLOWDOWN

        if inflation > 4:

            return Regime.RECOVERY

        return Regime.EXPANSION

# ============================================================
# PORTFOLIO REGIME MAPPER
# ============================================================

class PortfolioRegimeMapper:

    @staticmethod
    def map_regime(
        macro_regime
    ):

        if macro_regime in [

            Regime.EXPANSION,
            Regime.RECOVERY

        ]:

            return "bull"

        if macro_regime == Regime.SLOWDOWN:

            return "neutral"

        return "crisis"
