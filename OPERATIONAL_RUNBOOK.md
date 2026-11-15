# Operational Runbook

## Purpose

This runbook defines the controlled operational procedures for starting,
stopping, recovering, and responding to incidents affecting the production
portfolio system.

The procedures in this document are operational controls. They do not replace
the execution gate, risk controls, kill switch, circuit breakers, or other
production safety mechanisms.

## Critical Safety Principle

**Successful restart, successful state recovery, or healthy operational
status does not authorize trading execution.**

Execution authorization remains a separate control decision and must be
established through the applicable production execution gate and risk
controls.

Operational health is observational. Recovery restores operational state.
Neither mechanism independently grants authority to submit, approve, or
execute orders.

---

## Normal Startup

### Paper Worker Deployment

Use [PAPER_DEPLOYMENT_GUIDE.md](PAPER_DEPLOYMENT_GUIDE.md) for the release manifest,
hash-checked dependency install, exact-image transfer, full backup/restore tools,
evidence receipts and final qualification assessment. Compose requires an
explicit reviewed `PAPER_IMAGE`; systemd reads it from protected `.env.image`.

The paper worker is a one-shot process; run it from a host scheduler once per
trading day after the U.S. market close. Its internal lock prevents overlapping
cycles. The worker uses Yahoo Finance adjusted ETF prices and FRED macro data,
and requires `FRED_API_KEY` to be injected through the deployment secret store.

**Recommended host if no cloud account preference exists:** one Linux VM in
AWS Lightsail's Frankfurt region (`eu-central-1`), using the current 2 GB /
2 vCPU / 60 GB Linux plan (listed at USD 12/month before applicable taxes or
optional backups on the [Lightsail pricing page](https://aws.amazon.com/lightsail/pricing/)).
Frankfurt is an available Lightsail region according to the
[region list](https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-regions-and-availability-zones-in-amazon-lightsail.html).
This is
enough for a single daily worker and keeps the scheduler, persistent volume,
and logs together. Do not expose an application port; restrict SSH to the
operator's fixed IP, patch the guest OS, and limit outbound access to required
data and SMTP endpoints. AWS documents that guest OS patches and firewall
configuration remain customer responsibilities in its
[shared responsibility model](https://aws.amazon.com/compliance/shared-responsibility-model/).
Use an existing managed Linux host if one is already approved. Do not create a
billable instance until the owner selects the account and region.

### Recommended initial paper limits

| Setting | Initial value | Operating rule |
|---|---:|---|
| Runtime | Docker Compose on an isolated Linux VM | No inbound application ports; SSH restricted to the operator network. |
| Universe | Canonical 14 ETFs | Do not add assets during the first observation. |
| Simulated starting cash | $1,000,000 | Paper accounting only; no funds are connected. |
| Rebalance interval | 21 calendar days | Run the worker after each completed U.S. session; no-due cycles still report marks. |
| Cash buffer | 1% | Retain the configured cash reserve after target allocation. |
| Risk budget tolerance | `1e-6` | Keep strict fail-closed authorization. |
| Cost assumptions | 5 bps commission, 10 bps slippage | Confirm or replace with a documented conservative schedule before interpreting returns. |
| Observation period | 60 trading sessions and at least 3 completed rebalance cycles | Extend the period if data, alert, recovery, or reconciliation incidents occur. |

These are conservative paper-operation defaults, not a promise of returns or
approval for live execution. Do not set an alpha or return hurdle from these
defaults; strategy acceptance needs a separate point-in-time, out-of-sample
research review.

1. Provision a Linux host with Docker Engine and Docker Compose. Stage the
   reviewed release with `python -m paper_release stage`, build/scan that context
   in CI, and load the reviewed image on the host as described in the deployment
   guide. Set `PAPER_IMAGE` to its image ID or immutable registry digest.
2. Copy `.env.paper.example` to `.env.paper` in the deployment directory,
   inject the real FRED key from the host secret store, and keep `.env.paper`
   out of source control.
3. Keep the named `paper-state` volume persistent and back it up with the
   audit and report files.
4. Before scheduling, run `python -m paper_admin data-smoke`; it must report
   `PASS` with all 14 assets, current completed NYSE session, and macro fields.
   This check fetches data only and never runs a decision or order.
5. Install the provided `deploy/systemd/paper-worker.service` and
   `paper-worker.timer` from the deployment checkout. The timer runs at 17:15
   America/New_York Monday-Friday and handles daylight-saving changes. Follow
   [the systemd install and verification steps](deploy/systemd/README.md).
   The worker validates the latest completed NYSE session and fails closed if
   the feed is stale. If systemd is unavailable, use a single host scheduler
   with the same timezone and command; do not run two schedulers.
6. Monitor the service exit code, JSON report in `PAPER_REPORT_DIRECTORY`,
   append-only alerts in `PAPER_ALERT_FILE`, and the audit trail.
7. Do not remove the Docker volume or its SQLite lock file during a running
   cycle.

The worker refreshes `PAPER_DASHBOARD_FILE` after each cycle. To rebuild it
manually, run `python -m paper_dashboard --reports var/paper-reports --output
var/paper-dashboard.html`. It is a read-only summary of saved paper reports
and must not be exposed as a public web service.

The worker simulates fills at the latest adjusted close and applies the
configured accounting commission and slippage rates. The report includes
these assumptions, transaction costs, portfolio value, cash, marked positions,
cumulative return, benchmark-relative return, drawdown, turnover, data time,
decision/risk result, and reconciliation outcome. Performance figures are
measured from the paper session start and are not a backtest or a claim of
realistic intraday execution.

If the complete SMTP configuration is present, rejected/blocked decisions
and failed cycles also generate email notifications. Delivery is best-effort;
review the report's `notification` result and preserve the local alert file as
the durable alert record. Before paper observation begins, send a controlled
test alert and verify delivery with the named operator. Do not place SMTP
passwords in the checked-in example file.

The current runtime fills orders fully at the adjusted close. The broker and
OMS support partial fills and cancellation as lifecycle operations, but the
scheduled worker does not infer fill capacity from daily bars and does not
simulate queue position, bid/ask spread, market depth, delayed fills, or
market impact. Treat fill/cost outputs as configurable paper assumptions.
Before using the paper observation to assess strategy performance, choose and
document conservative rates and run separate execution stress scenarios.

### Daily Operator Review

After each scheduled cycle:

1. Confirm the report `status`, `data_as_of`, `data_source`, and market data
   freshness are expected for the session.
2. Review decision and risk validation status. A rejected or blocked result
   must have no submitted orders.
3. For an executed cycle, review each order's authorization decision ID,
   fill quantity/price, commission, estimated slippage cost, and reconciliation.
4. Review cash, NAV, positions/weights, cumulative costs, turnover,
   cumulative return, benchmark return, and drawdown against the approved
   limits.
5. Investigate every failure alert, reconciliation discrepancy, stale data
   result, or unexpected order before the next cycle.
6. Save the cycle report and alert evidence with the paper qualification log.

### State Backup and Restore

1. Stop the worker and confirm no cycle holds the service lock before backup.
2. Back up the database with `python -m paper_admin --database
   var/paper-state.sqlite3 backup /secure-backups/paper-state-<timestamp>.sqlite3`.
   This uses SQLite's online backup API and verifies the resulting database.
   Back up the audit log, reports, alerts, and the `var/research-snapshots/`
   artifact directory alongside it. These files are required to verify and
   replay historical decision events.
3. Store backups outside the runtime volume with access controls and a
   documented retention period.
4. Restore into an isolated directory and run
   `python -m paper_admin --database /restore/paper-state.sqlite3 verify`.
   Then verify the session snapshot schema, broker name, OMS active-order
   state, account health, and reconciliation state before resuming.
5. Treat an unresolved active order or reconciliation break as a manual
   recovery incident. Do not automatically resubmit it.

### Research Snapshot Replay

Replay is an offline diagnostic and never routes or submits orders. Run it
against the backed-up database and the matching research artifact directory:

```sh
python -m paper_admin --database /restore/paper-state.sqlite3 replay \
  --event-id paper-cycle:<cycle-id> \
  --snapshots /restore/research-snapshots
```

The command checks the database event chain, snapshot hash, input and
configuration fingerprints, and source/runtime provenance before recomputing
the decision. Any provenance mismatch or decision mismatch is a failed replay;
do not treat the stored result as reproduced. Keep snapshots and the event
database together under the same access and retention controls. Historical
FRED vintages are not reconstructed by this process.

### Stop and Kill Switch

Stop the scheduler first, then allow any active worker to complete or
terminate it under incident procedures. Preserve the logs and checkpoint
state. Do not edit persisted authorization or order records to force recovery.
The paper worker has no live broker route; kill-switch and circuit-breaker
controls remain independent operational checks. Record their state and the
operator who stopped or restarted the service.

1. Confirm the deployment uses the intended release and configuration.
2. Confirm required secrets and configuration are available through the
   approved configuration mechanism.
3. Confirm required market-data, persistence, audit, and operational
   dependencies are available.
4. Start the application or service.
5. Confirm startup completes without fatal errors.
6. Run the operational health check.
7. Confirm restart/state-recovery status is healthy where recovery is required.
8. Confirm the audit trail is operational.
9. Confirm alerting and notification infrastructure is operational.
10. Confirm kill-switch and circuit-breaker controls are available.
11. Confirm required risk and execution controls are healthy.
12. Record the startup event and relevant operational status.
13. **Do not infer trading authorization from successful startup or health.**
14. Trading execution may proceed only after the applicable execution
    authorization and risk controls independently pass.

### Startup Failure

If startup fails:

- Do not attempt to bypass the failing control.
- Preserve the failure information and relevant logs.
- Do not authorize execution.
- Determine whether the failure is configuration, dependency, recovery,
  health, audit, alerting, or execution-control related.
- Escalate according to the Incident Escalation procedure when required.

---

## Normal Shutdown

1. Stop new execution activity through the approved operational control.
2. Confirm no unauthorized orders are being submitted.
3. Allow already-authorized operational work to reach a safe stopping point
   where applicable.
4. Persist required operational and recovery state.
5. Confirm audit information has been recorded.
6. Confirm shutdown completed without unresolved fatal errors.
7. Record the shutdown event and relevant operational status.
8. Verify that a subsequent restart will not treat shutdown as execution
   authorization.

A normal shutdown must leave the system in a state that can be safely
restarted without bypassing execution controls.

---

## Abnormal Restart

An abnormal restart includes process termination, host restart, crash,
unexpected service interruption, or other termination outside the normal
shutdown procedure.

1. Treat the system as **not authorized to execute** until independently
   revalidated.
2. Preserve available logs, audit events, error information, and timestamps.
3. Restart the application using the approved startup procedure.
4. Invoke restart/state recovery.
5. Verify that persisted state is compatible with the running component
   versions.
6. Verify that registered components recover successfully.
7. Run the operational health check.
8. Verify audit and alerting status.
9. Verify kill-switch and circuit-breaker availability.
10. Re-establish execution authorization only through the normal independent
    execution-control process.

A successful abnormal restart does not bypass any execution gate.

---

## Recovery Failure

A recovery failure occurs when persisted operational state cannot be restored
safely or when one or more required components fail recovery.

When recovery fails:

1. **Fail closed.**
2. Do not authorize trading execution.
3. Do not manually substitute unverified state for persisted state.
4. Preserve the recovery error and associated operational events.
5. Identify the failed component or state record.
6. Verify whether the failure is caused by corruption, incompatible API
   version, missing component registration, dependency failure, or another
   controlled cause.
7. Escalate the incident when recovery cannot be safely completed.
8. Only resume normal operation after state integrity and operational health
   have been independently established.
9. Re-establish execution authorization separately through the applicable
   execution controls.

Recovery failure must never be converted into execution permission merely
because the process itself is running.

---

## Kill Switch Incident

A kill-switch incident occurs when the kill switch is activated, unavailable,
unexpectedly triggered, or suspected to be required.

### Immediate Response

1. Treat the system as execution-restricted.
2. Confirm the current kill-switch state.
3. Prevent new execution activity while the incident is assessed.
4. Preserve relevant operational events, audit records, alerts, and logs.
5. Determine the reason for activation or suspected activation.
6. Assess current positions, outstanding orders, and operational exposure
   through the approved controls.
7. Escalate to the responsible human operator.

### Recovery

The kill switch must not be bypassed to restore normal execution.

Before any return to execution:

- the incident cause must be understood;
- required safety controls must be healthy;
- the kill-switch state must be explicitly verified;
- required human approval must be obtained;
- execution authorization must be independently re-established.

---

## Circuit Breaker Incident

A circuit-breaker incident occurs when a circuit breaker trips, remains open,
cannot reset, or indicates that an execution safety threshold has been
breached.

1. Treat the circuit breaker as an execution restriction.
2. Do not bypass or force-reset the protection merely to resume trading.
3. Preserve the associated event, audit record, alert, and logs.
4. Identify the condition that caused the circuit breaker to activate.
5. Assess relevant portfolio, market-data, execution, and risk conditions.
6. Confirm operational health.
7. Escalate to the responsible human operator where required.
8. Reset the circuit breaker only through the approved control procedure.
9. Re-establish execution authorization independently before resuming
   execution.

A circuit-breaker reset is not itself an execution authorization.

---

## Operational Health Failure

Operational health failures include unhealthy restart recovery, unavailable
dependencies, failed monitoring checks, or other conditions indicating that
the operational system cannot be considered healthy.

1. Treat the system as operationally restricted.
2. Do not infer execution authorization from partial health.
3. Identify which health component failed.
4. Preserve the health result, timestamps, logs, and relevant audit events.
5. Determine whether the failure affects state recovery, persistence,
   auditability, alerting, execution controls, or other safety mechanisms.
6. Correct the underlying operational condition using the approved procedure.
7. Re-run the health check.
8. Confirm all required safety controls are independently healthy.
9. Obtain human approval where required.
10. Re-establish execution authorization separately.

---

## Alert and Audit Failure

### Alert Failure

If alert delivery fails:

1. Record the alert failure as an operational incident.
2. Preserve the original event and available logs.
3. Determine whether the notification transport is unavailable,
   misconfigured, or otherwise failing.
4. Do not assume that an undelivered alert means the underlying event did
   not occur.
5. Escalate according to incident severity.
6. Restore alert delivery before relying on normal operational notification.

### AuditTrail Failure

If the AuditTrail is unavailable or fails to record an operational event:

1. Treat the loss of auditability as an operational control failure.
2. Preserve all available logs and event information.
3. Do not silently discard or rewrite the missing audit event.
4. Determine whether the failure is transient or persistent.
5. Escalate according to incident severity.
6. Restore audit functionality.
7. Reconcile available operational evidence before normal operation resumes.
8. Do not treat restoration of the AuditTrail as execution authorization.

---

## Incident Escalation

Escalate an incident when any condition could compromise:

- execution safety;
- portfolio or position controls;
- restart/state integrity;
- auditability;
- alerting;
- kill-switch availability;
- circuit-breaker protection;
- operational health;
- configuration or secrets integrity.

### Escalation Sequence

1. Apply the immediate fail-closed control appropriate to the incident.
2. Preserve logs, operational events, audit records, and timestamps.
3. Notify the responsible operator or incident owner.
4. Describe the observed condition, affected component, and current control
   state.
5. Record actions already taken.
6. Identify whether execution is currently authorized or restricted.
7. Obtain **human approval** before any action that restores or changes
   execution authority where required.
8. Document the resolution and validation performed after recovery.

No operator should infer execution authorization solely from process
availability, restart success, state recovery, operational health, alert
delivery, or audit restoration.

---

## Post-Incident Validation

After a material operational incident:

1. Confirm the triggering condition has been resolved.
2. Confirm operational health is healthy.
3. Confirm restart/recovery state is consistent where applicable.
4. Confirm AuditTrail functionality.
5. Confirm alerting functionality.
6. Confirm kill-switch availability.
7. Confirm circuit-breaker availability.
8. Confirm execution and risk controls independently pass.
9. Obtain required human approval.
10. Record the incident outcome and validation evidence.

The post-incident validation process must preserve the separation between
operational recovery and execution authorization.

---

## Operational Evidence

For material incidents and recovery events, retain available:

- timestamps;
- operational events;
- audit records;
- health results;
- recovery results;
- alerts and notification outcomes;
- relevant logs;
- kill-switch state;
- circuit-breaker state;
- execution-control state;
- human approvals and decisions.

Operational evidence should be sufficient to reconstruct what happened,
which controls were active, and whether execution was authorized at the time.

---

## Authority Boundary

The operational runbook does not grant execution authority.

**A successful restart does not authorize execution.**

**Healthy operational status does not authorize execution.**

**Successful state recovery does not authorize execution.**

**Kill-switch reset does not authorize execution.**

**Circuit-breaker reset does not authorize execution.**

Execution authority must remain a separate, explicit, independently validated
decision governed by the production execution gate and applicable risk and
safety controls.
