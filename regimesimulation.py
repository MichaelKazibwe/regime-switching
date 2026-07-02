import numpy as np

# ============================================================
# REGIME MONTE CARLO
# ============================================================

class RegimeMonteCarlo:

    @staticmethod
    def simulate_states(
        transition_matrix,
        start_state,
        horizon=252,
        n_sims=1000
    ):

        simulations = []

        n_states = transition_matrix.shape[0]

        for _ in range(n_sims):

            state = start_state

            path = [state]

            for _ in range(horizon):

                state = np.random.choice(
                    np.arange(n_states),
                    p=transition_matrix[state]
                )

                path.append(state)

            simulations.append(path)

        return np.array(simulations)


# ============================================================
# REGIME PORTFOLIO SIMULATOR
# ============================================================

class RegimePortfolioSimulator:

    @staticmethod
    def simulate_returns(
        state_paths,
        state_return_map
    ):

        terminal_returns = []

        for path in state_paths:

            cumulative = 1.0

            for state in path:

                mu = state_return_map[state]

                daily_return = np.random.normal(
                    mu,
                    abs(mu) + 0.01
                )

                cumulative *= (
                    1.0 + daily_return
                )

            terminal_returns.append(
                cumulative - 1.0
            )

        return np.array(
            terminal_returns
        )


# ============================================================
# REGIME SIMULATION ANALYTICS
# ============================================================

class RegimeSimulationAnalytics:

    @staticmethod
    def summary(
        simulations
    ):

        return {

            "mean_terminal":
                simulations.mean(),

            "median_terminal":
                np.median(simulations),

            "5pct":
                np.percentile(
                    simulations,
                    5
                ),

            "1pct":
                np.percentile(
                    simulations,
                    1
                ),

            "95pct":
                np.percentile(
                    simulations,
                    95
                )

        }