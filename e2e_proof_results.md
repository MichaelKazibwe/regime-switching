# REGIME SWITCHING SYSTEM

# END-TO-END PROOF RESULTS

Generated: `2026-11-15T08:45:15.700900+00:00`

> **EXECUTABLE E2E EVIDENCE ARTIFACT**

## Executive Status

- Total proofs: **54**
- PASS: **54**
- FAIL: **0**
- BLOCKED: **0**
- NOT_EXECUTED: **0**
- SKIPPED: **0**
- Deployment proof: **PROVEN**

## Safety Boundary

- Live trading enabled: **NO**
- Live broker connection: **NO**
- Network execution: **NO**
- Git mutation: **NO**
- Source matrix mutation: **NO**
- Execution mode: **PAPER / IN-MEMORY ONLY**

## Proof Results

| ID | Phase | Boundary | Status | Evidence | Error |
|---|---|---|---|---|---|
| E2E-01 | A | Decision generation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-02 | A | Decision identity | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-03 | A | Risk validation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-04 | A | Execution authorization | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-05 | A | Authorization status | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-06 | A | Authorization state | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-07 | A | Risk authorization invariant | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-08 | B | Canonical order creation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-09 | B | OMS registration | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-10 | B | Order identity | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-11 | C | Authorized order intent | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-12 | C | Intent validation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-13 | C | Order identity preservation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-14 | C | Authorization identity preservation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-15 | D | Execution handoff | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-16 | D | Execution handoff validation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-17 | D | Execution order provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-18 | D | Decision provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-19 | E | Routing handoff | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-20 | E | Routing authorization | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-21 | E | Routing provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-22 | F | Raw order routing hard stop | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-23 | F | Raw routing mutation protection | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-24 | F | Explicit broker bypass hard stop | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-25 | G | Authorized routing | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-26 | G | Routing identity | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-27 | G | Broker health | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-28 | H | Paper broker submission | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-29 | H | Broker order identity | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-30 | H | Broker lifecycle | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-31 | H | OMS/broker separation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-32 | I | Broker execution | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-33 | I | Receipt identity | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-34 | I | Receipt quantity | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-35 | I | Receipt price | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-36 | J | Authorized receipt execution | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-37 | J | Execution result identity | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-38 | J | Execution provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-39 | K | Execution accounting delegation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-40 | L | Cash accounting | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-41 | L | Position accounting | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-42 | L | Trade creation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-43 | M | OMS order lifecycle | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-44 | M | OMS execution result | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-45 | M | OMS execution handoff | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-46 | N | Decision provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-47 | N | Order provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-48 | N | Regime provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-49 | N | Authorization provenance | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-50 | O | OMS/broker reconciliation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-51 | O | Quantity reconciliation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-52 | O | Price reconciliation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-53 | O | Account reconciliation | 🟢 PASS | Executable assertion completed successfully. |  |
| E2E-54 | O | End-to-end completion | 🟢 PASS | Executable assertion completed successfully. |  |

## Acceptance Rule

The system is NOT considered proven unless all mandatory E2E proofs PASS.

A BLOCKED result is not a PASS and is not converted into a PASS.

The result is evidence only and does not authorize live trading.
