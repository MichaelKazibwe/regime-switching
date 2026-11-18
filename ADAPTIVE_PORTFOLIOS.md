# Current-data allocation and aggregate weekly strategy

The weekly short-, medium- and long-horizon candidates refit target capital weights from the most recently completed trading week in the verified market capture. The dynamic daily strategy refits its engine mix from each verified daily market context. Neither uses preset strategy percentages as its current target. Saved client mandates and immutable historical benchmarks remain dated references; changes to them require a new proposal/review rather than rewriting their history.

## Weekly construction

- Eligibility comes from the global asset registry and actual available price history, not a fixed ETF list or a fixed asset count. At least 156 complete weekly returns across eight eligible assets are required. Missing data are not filled to admit an instrument.
- Each horizon uses up to 104 weeks of returns. Annual covariance is 70% sample covariance plus 30% of its diagonal. The clipped historical mean/momentum estimate is shrunk towards zero using its sampling variance. These inputs are estimates, not established forecasting alpha.
- The constrained objective rewards estimated return and penalizes covariance risk, historical tail loss, drawdown and concentration. Risk aversion, cash/equity limits, individual-asset caps and diversification constraints are declared safeguards, not target asset weights. The optimizer can retain additional cash when the growth/risk trade-off is unattractive.
- Positions initially smaller than 0.25% are removed from the eligible support, and the optimizer solves again with the original constraints. This avoids normalizing small positions in a way that would break risk limits. The resulting asset count varies with market inputs; it is not a claim of globally optimal cardinality.
- The new **Adaptive aggregate strategy** optimizes proportions of the current short-, medium- and long-horizon allocations plus an explicit cash sleeve. Its objective uses the same current return/risk inputs with tail-loss, drawdown and concentration penalties. It aggregates capital by symbol, so an asset appearing in several horizons is counted once. Strategy proportions and the final asset/risk weights are disclosed.
- The aggregate optimizes within those feasible sleeves; it is not a global search over every possible asset combination. Sleeve diagnostics apply today's fitted weights to historical observations. They are not realized historical sleeve strategy returns.

## Daily strategy construction

`DYNAMIC_GROWTH_RESILIENCE_V2_ADAPTIVE` recomputes its four engine proposals, then fits their nonnegative proportions summing to one using current covariance and shrunk observed momentum. Legacy regime lookup percentages are not used. The blended target is independently projected and verified against exposure, volatility, bucket, satellite and signed risk-contribution limits. Macro data quality safeguards remain in force.

The new strategy requires a separate forward cohort. Old cohort databases and their performance remain immutable and must not be combined with the revised strategy's prospective results.

## Refresh, evaluation and review

The registered daily pipeline refreshes verified data and runs the weekly publisher when its market inputs, dashboard evidence or source identity change. Weekly decision prices stop at the latest fully closed trading week; a page refresh does not manufacture newer weekly observations. While visible, the weekly page checks for newly published recommendations every minute and on returning to the tab.

Each weekly candidate includes holdings, capital weights, signed variance contributions, diversification labels, same-period causal historical replay, hypothetical stresses and conditional monthly/quarterly/annual projections. The PDF and JSON include the aggregate and its strategy proportions. Historical replay refits at each decision origin and fills at the following weekly close with modeled transaction costs. Horizon replay also penalizes turnover against held pre-decision weights; aggregate sleeve fitting includes concentration regularization, while its replay deducts actual modeled turnover costs. Projections retain the current target weights rather than claiming to simulate future optimizer decisions.

Recommendations remain subject to client research review. Maximizing growth while minimizing risk and drawdown is a trade-off; no algorithm can guarantee all three objectives or eliminate financial loss. Current forecasts, historical replay and resampling do not establish outperformance or calibrated future loss limits. Trading and automatic model promotion remain disabled.
