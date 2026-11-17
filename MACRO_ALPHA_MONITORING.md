# Macro alpha testing monitor

Macro alpha research monitoring is enabled system-wide. The authenticated dashboard, cycle benchmark, weekly portfolios and observation APIs expose one shared `macro_alpha` signal. The Macro outlook view shows its probabilities, inputs, exclusions, training-label cutoff and prospective outcome counters. A persistent dashboard button makes its status visible from every view. Daily refresh and the daily research trainer use the same source-bound implementation.

The monitor is a separate research challenger. It predicts the released-condition macro quadrant 63 completed market sessions ahead. It does not predict portfolio returns, establish investment alpha or override portfolio weights, risk budgets, drawdown guards, the incumbent predictive gate or order controls.

## Partial inputs

The full incumbent requires exact monthly observation periods, including CPI endpoints. A missing required CPI month prevents the full feature vector from being declared valid. Testing does not create that observation. The new challenger fits on the subset of macro components available at the current decision timestamp: production growth, unemployment change, inflation change and the Treasury curve are admitted independently. Missing components are excluded and disclosed, never filled or set to neutral values.

The current capture supports production growth, unemployment change and the yield curve. Inflation change is excluded because a required CPI observation is absent. The full-input incumbent retains its data quarantine. Native series freshness, vintage availability and exact monthly endpoints remain enforced.

The challenger uses a standardized logistic classifier with fixed C=1, a 1,260-session training window, at least 252 valid training examples and a 63-session label purge. Only historical rows with complete valid macro inputs and valid matured target labels enter training. Its displayed probabilities blend 25% model probabilities with 75% smoothed historical regime frequency. These parameters are declared research choices, not proof of optimality. Excluding incomplete historical examples can introduce selection bias.

## Genuine forward monitoring

`pilot_daily.py` records an immutable forecast for the actual latest completed market session before preparing the portable research snapshot. `macro_alpha.py` can also run the same monitor directly. No historical rows are inserted into the prospective stream. An observation is identified by market session and source/settings/feature-mask protocol. Repeating identical evidence is idempotent; changing sealed evidence within that protocol is rejected. A changed protocol starts its own counts.

Once 63 market sessions elapse, scores compare the originally issued probabilities with the as-known target regime using Brier loss and the stored frequency baseline. Immature outcomes remain pending. Mature outcomes lacking valid macro labels are counted separately as unscorable, not silently removed or presented as successes. No automatic promotion or alpha-established flag follows from a small sample. Source history and runtime receipts remain under ignored `var/macro-alpha/`.

The shared signal is available at `/api/macro-alpha` after login, and in the `macro_alpha` member of `/api/dashboard`, `/api/benchmark`, `/api/observations` and `/api/weekly`. `/api/macro-monitor` includes the same signal beside daily observations and quarterly aggregates. The weekly PDF includes a dated research-monitor section, separate from the week-close portfolio calculations.

For testing, inspect input coverage and exclusions, verify probability normalization and the training-label cutoff, then collect genuine sessions. Review scored outcome count, Brier differences against the baseline, regime coverage, calibration and uncertainty before considering any portfolio use. Execution, automatic promotion and portfolio activation remain disabled for this challenger.
