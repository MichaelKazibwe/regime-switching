import pandas as pd

# ============================================================
# PERFORMANCE ATTRIBUTION
# ============================================================

class PerformanceAttribution:

    def contribution(
        self,
        weights,
        returns
    ):

        contributions = (

            weights
            *
            returns
        )

        return contributions

    def summary(
        self,
        weights,
        returns
    ):

        contrib = (
            self.contribution(
                weights,
                returns
            )
        )

        return pd.DataFrame({

            "weight":
                weights,

            "return":
                returns,

            "contribution":
                contrib
        })
