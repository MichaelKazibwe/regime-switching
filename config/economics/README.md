# Optional observed user cash history

The example is deliberately unverified and rejected by the assessment.
Configure actual history privately, outside committed configuration. Never put
account identifiers, passwords or a bank statement in this directory.

Use a CSV with `date,net_return`: one ordered unique naive NYSE session date per
row and the actual effective net cash return accrued between the prior and
current valuation close. Include weekend accrual in the appropriate observed
session; do not divide an annual quote by 252 and call it observed history.
Returns are decimal fractions, after applicable account fees. They are
historical realized accrual, not a forward estimate used to choose trades.
The manifest identifies USD, a named reviewer/source, a SHA256 for that CSV,
and at least one protected evidence file/hash. File names must be contained
siblings. Every requested comparison date must have an actual finite return;
no rate filling or substitution is performed.

A local `verified: true` is an operator attestation, not independent bank
verification, an authenticity signature or public investment approval. A
mismatched file hash fails. The current assessment has no such configured
history, so its user cash-history gate remains blocked.

SGOV data are an observed ETF reserve comparison. Its adjusted returns include
fund behavior and distributions; it is not deposit cash, guaranteed principal,
a known future yield or a universally accessible account product.
