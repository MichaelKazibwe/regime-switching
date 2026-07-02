from forwardriskmetrics import ForwardRiskMetrics

from regimesimulation import (
    RegimeMonteCarlo,
    RegimePortfolioSimulator,
    RegimeSimulationAnalytics,
)

# ============================================================
# FORWARD RISK ANALYZER
# ============================================================

class MonteCarloBacktestAnalyzer:

    def __init__(

        self,

        horizon=252,

        simulations=1000

    ):

        self.horizon = horizon

        self.simulations = simulations

    def run(

        self,

        transition_matrix,

        start_state,

        state_return_map

    ):

        # ============================================
        # SIMULATE REGIME PATHS
        # ============================================

        paths = (

            RegimeMonteCarlo

            .simulate_states(

                transition_matrix,

                start_state,

                horizon=self.horizon,

                n_sims=self.simulations

            )

        )

        # ============================================
        # SIMULATE PORTFOLIO RETURNS
        # ============================================

        terminal_returns = (

            RegimePortfolioSimulator

            .simulate_returns(

                paths,

                state_return_map

            )

        )

        # ============================================
        # SUMMARY STATISTICS
        # ============================================

        summary = (

            RegimeSimulationAnalytics

            .summary(

                terminal_returns

            )

        )

# ============================================
# FORWARD RISK METRICS
# ============================================

        risk_metrics = (

            ForwardRiskMetrics

            .summarize(

                terminal_returns

            )

        )

        return {

            "paths": paths,

            "terminal_returns": terminal_returns,

            "summary": summary,

            "risk_metrics": risk_metrics

        }