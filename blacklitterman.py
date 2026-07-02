import numpy as np

# ============================================================
# BLACK-LITTERMAN
# ============================================================

class BlackLittermanModel:

    def __init__(
        self,
        tau=0.05
    ):

        self.tau = tau

    def equilibrium_returns(
        self,
        covariance,
        market_weights,
        risk_aversion=2.5
    ):

        return (

            risk_aversion

            *

            covariance

            @

            market_weights

        )

    def posterior_returns(
        self,
        covariance,
        market_weights,
        views,
        confidence=0.25
    ):

        pi = (

            self.equilibrium_returns(
                covariance,
                market_weights
            )

        )

        n_assets = len(pi)

        P = np.eye(
            n_assets
        )

        Q = np.asarray(
            views,
            dtype=float
        )

        omega = (

            np.eye(
                n_assets
            )

            *

            confidence

        )

        tau_sigma = (
            self.tau
            *
            covariance
        )

        posterior = (

            np.linalg.inv(

                np.linalg.inv(
                    tau_sigma
                )

                +

                P.T
                @
                np.linalg.inv(
                    omega
                )
                @
                P

            )

            @

            (

                np.linalg.inv(
                    tau_sigma
                )
                @
                pi

                +

                P.T
                @
                np.linalg.inv(
                    omega
                )
                @
                Q

            )

        )

        return posterior
