"""Read-only roadmap items 25/26 monitor, backup drill and reviewed alert outbox."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import time

import numpy as np
from observation_watchdog import check
from forward_cohort import database as cohort_database
from operational_metrics import MetricStore
from operational_escalation import EscalationStore
from operational_recovery import snapshot, drill, nav_replay
from strategy_degradation import analyze as strategy_analysis, feature_drift
from execution_degradation import analyze as execution_analysis
from risk_forecast_registry import register
from portfolio_contract import extended_prices
from strategy_integrity import strict_json, fingerprint
from strategy_receipts import atomic_json

DEFAULT_SLO = dict(
    post_close_max_seconds=7200,
    heartbeat_max_seconds=7200,
    ack_p95_seconds=5,
    callback_p95_seconds=5,
    shortfall_excess_bps=10,
    rto_seconds=900,
    escalate_seconds=900,
    realized_to_modeled_volatility=1.5,
)


def configuration(path):
    if path is None:
        return dict(delivery_enabled=False, broker_evidence=None, slo=DEFAULT_SLO)
    path = Path(path)
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("Owner-only operational configuration required")
    c = strict_json(path)
    c["slo"] = {**DEFAULT_SLO, **c.get("slo", {})}
    if set(c["slo"]) != set(DEFAULT_SLO) or any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not np.isfinite(v)
        or v <= 0
        for v in c["slo"].values()
    ):
        raise ValueError("Positive finite declared SLOs required")
    return c


def email_sender(c, now):
    if c.get("delivery_enabled") is not True:
        return None
    if c.get("delivery_authorized") is not True or len(c.get("recipients", [])) != 2:
        raise PermissionError(
            "Explicit primary/escalation delivery authorization required"
        )
    from emailtransport import EmailTransport
    from operationalevent import OperationalEvent

    # Secrets remain in the protected configuration or its process environment.
    password = (
        os.environ[c["smtp_password_environment"]]
        if c.get("smtp_password_environment")
        else None
    )
    transport = EmailTransport(
        smtp_host=c["smtp_host"],
        smtp_port=c.get("smtp_port", 587),
        sender=c["sender"],
        username=c.get("smtp_username"),
        password=password,
        use_tls=True,
        timeout=10,
    )

    def send(record):
        event = OperationalEvent.create(
            event_type="LIVE_PLATFORM_P1_REVIEW",
            severity="CRITICAL" if record["level"] else "ERROR",
            source="SYSTEM",
            message="Operational review required: " + record["signal"],
            timestamp=now.isoformat(),
        )
        result = transport.send(
            notification_id=record["notification_id"],
            event=event,
            recipient=c["recipients"][record["level"]],
        )
        return dict(
            accepted=result.delivered is True, reference=record["notification_id"]
        )

    return send


def run(root="var/live-upgrade-p1", config=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.monotonic()
    c = configuration(config)
    slo = c["slo"]
    with (root / "monitor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # SLO targets are prospective declarations; old sessions are diagnostics, not retroactive qualification.
        if not (root / "slo-policy.json").exists():
            atomic_json(
                root / "slo-policy.json",
                dict(declared_at=now.isoformat(), targets=slo, execution_enabled=False),
                exclusive=True,
            )
        elif strict_json(root / "slo-policy.json")["targets"] != slo:
            raise ValueError("Changed SLOs require a new monitor version/directory")
        report = dict(
            status="RUNNING",
            checked_at=now.isoformat(),
            execution_enabled=False,
            release_approved=False,
            signals=[],
            external_delivery_verified=False,
        )
        incidents = EscalationStore(root / "escalation.sqlite3")
        try:
            watch = check(now=now)
            report["watchdog"] = watch
            pending_runs = sorted(
                Path("var/live-observation-cycle/runs").glob("*/receipt.json")
            )
            if pending_runs:
                active = strict_json(pending_runs[-1])
                age = (
                    now - datetime.fromisoformat(active["started_at"])
                ).total_seconds()
                if active.get("status") == "RUNNING" and 0 <= age <= 7500:
                    report["status"] = "PENDING_COHORT_ADVANCE"
                    report["delivery"] = incidents.dispatch(
                        email_sender(c, now),
                        now=now,
                        escalate_seconds=slo["escalate_seconds"],
                    )
                    return report
            if watch["status"] == "ALERT_REQUIRED":
                report["signals"].append("OBSERVATION_SLO_BREACH")
            if shutil.disk_usage(root).free < 512 * 1024**2:
                report["signals"].append("DISK_RESERVE_LOW")
            job = strict_json("var/strategy-operations-integrated-v1/latest-job.json")
            if job["status"] != "PASSED_SHADOW_ONLY":
                raise ValueError(
                    "Validated daily bundle required for diagnostics/recovery"
                )
            bundle = Path(job["job"]) / "dashboard/latest-strategy-run.json"
            from tradingcalendar import TradingCalendar
            from datetime import timedelta

            close = (
                TradingCalendar()
                .session(watch["core"]["expected_session"])["market_close"]
                .to_pydatetime()
            )
            policy = strict_json(root / "slo-policy.json")
            actual = (
                datetime.fromisoformat(job["finished_at"])
                if job.get("market_session") == watch["core"]["expected_session"]
                else now
            )
            lag = max(0, (actual - close).total_seconds())
            applicable = close >= datetime.fromisoformat(policy["declared_at"])
            report["freshness_slo"] = dict(
                seconds_after_completed_close=lag,
                target_seconds=slo["post_close_max_seconds"],
                post_policy_session=applicable,
                breach=applicable and lag > slo["post_close_max_seconds"],
            )
            if report["freshness_slo"]["breach"]:
                report["signals"].append("POST_CLOSE_FRESHNESS_SLO_BREACH")
            heartbeat = strict_json("var/local-observation-scheduler/heartbeat.json")
            if now - datetime.fromisoformat(heartbeat["checked_at"]) > timedelta(
                seconds=slo["heartbeat_max_seconds"]
            ):
                report["signals"].append("WORKER_HEARTBEAT_SLO_BREACH")
            b = strict_json(bundle)
            prices = extended_prices(b["capture"], b["benchmark_extension"])
            databases = dict(
                core=cohort_database("var/strategy-operations-integrated-v1"),
                engines=cohort_database("var/return-engine-shadow-v1"),
                dynamic=cohort_database("var/dynamic-forward-v1"),
            )
            report["degradation"] = {}
            for name, database in databases.items():
                forecasts = register(
                    database,
                    prices,
                    root / "risk-forecasts" / name,
                    cohort=name,
                    now=now,
                )
                report["degradation"][name] = strategy_analysis(
                    database, risk_forecasts=forecasts
                )
            features = strict_json(Path(b["training_report"]).parent / "features.json")
            report["feature_drift"] = feature_drift(features)
            if report["feature_drift"].get("review_features"):
                report["signals"].append("FEATURE_DISTRIBUTION_REVIEW")
            for cohort in report["degradation"].values():
                calibration = cohort["calibration"]
                if (
                    calibration["nonoverlapping_outcomes"] >= 12
                    and calibration["model_brier"] > calibration["baseline_brier"]
                ):
                    report["signals"].append("FORECAST_CALIBRATION_REVIEW")
                for item in cohort["strategies"].values():
                    if any(
                        (
                            f.get("ratio", 0) is not None
                            and f.get("ratio", 0)
                            > slo["realized_to_modeled_volatility"]
                        )
                        or (
                            f.get("status") == "MATURED_GROSS_PRICE_RISK"
                            and f.get("predicted") == 0
                            and f.get("realized", 0) > 0.001
                        )
                        for f in item["risk_forecasts"]
                    ):
                        report["signals"].append("REALIZED_RISK_REVIEW")
            execution = execution_analysis(c.get("broker_evidence"), now=now)
            report["execution"] = execution
            report["execution_slo"] = dict(status="UNAVAILABLE_NO_BROKER_EVIDENCE")
            if execution["orders"]:
                a = [
                    r["ack_seconds"]
                    for r in execution["rows"]
                    if r["ack_seconds"] is not None
                ]
                callbacks = [
                    v for r in execution["rows"] for v in r["callback_seconds"]
                ]
                report["execution_slo"] = dict(
                    ack_p95=float(np.quantile(a, 0.95)) if a else None,
                    callback_p95=float(np.quantile(callbacks, 0.95))
                    if callbacks
                    else None,
                )
                if (
                    a
                    and report["execution_slo"]["ack_p95"] > slo["ack_p95_seconds"]
                    or callbacks
                    and report["execution_slo"]["callback_p95"]
                    > slo["callback_p95_seconds"]
                ):
                    report["signals"].append("EXECUTION_LATENCY_SLO_BREACH")
                if any(
                    r["shortfall_bps"] is not None
                    and r["shortfall_bps"] - r["modeled_bps"]
                    > slo["shortfall_excess_bps"]
                    for r in execution["currencies"].values()
                ):
                    report["signals"].append("IMPLEMENTATION_SHORTFALL_REVIEW")
            heads = {name: nav_replay(p)["chain_head"] for name, p in databases.items()}
            backup_index = root / "backup-latest.json"
            saved = strict_json(backup_index) if backup_index.exists() else {}
            if saved.get("heads") != heads:
                key = now.strftime("%Y%m%dT%H%M%S%fZ")
                location = root / "backups" / key
                snapshot(databases, bundle, location, now=now)
                recovery = drill(
                    location,
                    root / "restore-drills" / key,
                    rto_seconds=slo["rto_seconds"],
                )
                if recovery["status"] != "LOCAL_RESTORE_OBJECTIVE_PASS":
                    report["signals"].append("RESTORE_RTO_BREACH")
                saved = dict(
                    heads=heads,
                    backup=str(location),
                    drill=recovery,
                    verified_at=now.isoformat(),
                )
                atomic_json(backup_index, saved)
            else:
                # Verify retained artifacts rather than copying the same data every five minutes.
                from shadow_bundle_backup import verify_backup

                for name, head in heads.items():
                    if (
                        verify_backup(Path(saved["backup"]) / name)["chain_head"]
                        != head
                    ):
                        raise ValueError("Backup no longer matches committed state")
            report["recovery"] = dict(
                protected_heads=heads,
                unbacked_commits=0,
                local_drill=saved["drill"],
                objective="Every newly observed cohort head backed up and restore-tested within the next monitoring cycle; zero committed-event loss at this check",
                off_host_verified=False,
                managed_broker_database="UNAVAILABLE_NOT_CONFIGURED",
            )
            if c.get("managed_database"):
                from managed_disaster_recovery import (
                    backup as backup_account,
                    restore as restore_account,
                )

                key = now.strftime("%Y%m%dT%H%M%S%fZ")
                # Managed broker state is small in the initial single-host pilot;
                # never infer a database path or touch it when unconfigured.
                location = root / "managed-backups" / key
                original = backup_account(c["managed_database"], location)
                restored = restore_account(
                    location,
                    root / "managed-restore-drills" / key,
                    rto_seconds=slo["rto_seconds"],
                )
                report["recovery"]["managed_broker_database"] = dict(
                    backup=original, restore=restored
                )
            report["signals"] = sorted(set(report["signals"]))
            report["status"] = (
                "REVIEW_REQUIRED"
                if report["signals"]
                else "LOCAL_MONITOR_PASS_QUALIFICATION_BLOCKED"
            )
            report["review_actions"] = [
                "Review/freeze/refit decisions require named operator/model approval; no automatic promotion or trading-state change."
            ]
            incidents.reconcile(report["signals"], now=now)
            report["delivery"] = incidents.dispatch(
                email_sender(c, now), now=now, escalate_seconds=slo["escalate_seconds"]
            )
        except Exception as exc:
            report.update(status="FAILED", error_type=type(exc).__name__)
            with incidents.connect() as db:
                unresolved = [
                    r[0]
                    for r in db.execute(
                        "SELECT signal FROM incidents WHERE resolved IS NULL"
                    )
                ]
            report["signals"] = sorted(
                set([*unresolved, "P1_MONITOR_INTEGRITY_OR_RUNTIME_FAILURE"])
            )
            incidents.reconcile(report["signals"], now=now)
            try:
                report["delivery"] = incidents.dispatch(
                    email_sender(c, now),
                    now=now,
                    escalate_seconds=slo["escalate_seconds"],
                )
            except Exception as delivery_error:
                report["delivery"] = dict(
                    status="DELIVERY_CONFIGURATION_OR_STORAGE_FAILURE",
                    error_type=type(delivery_error).__name__,
                )
            raise
        finally:
            report["elapsed_seconds"] = time.monotonic() - started
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(
                root / "runs" / (now.strftime("%Y%m%dT%H%M%S%fZ") + ".json"),
                report,
                exclusive=True,
            )
            atomic_json(root / "latest.json", report)
            metrics = dict(
                regime_monitor_failed=int(report["status"] == "FAILED"),
                regime_open_review_signals=len(report["signals"]),
                regime_monitor_duration_seconds=report["elapsed_seconds"],
                regime_broker_evidence_available=int(
                    report.get("execution", {}).get("orders", 0) > 0
                ),
            )
            store = MetricStore(root / "metrics.sqlite3")
            store.record(now, metrics, fingerprint(report), report)
            from productreport import private_write

            private_write(root / "metrics.prom", store.prometheus())
        return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="var/live-upgrade-p1")
    p.add_argument("--configuration")
    p.add_argument("--ack-incident")
    p.add_argument(
        "--review-decision",
        choices=["HOLD", "REQUEST_FREEZE", "REQUEST_REFIT", "REJECT_CANDIDATE"],
    )
    p.add_argument("--reason")
    p.add_argument("--strategy")
    p.add_argument("--candidate-version")
    a = p.parse_args()
    if a.ack_incident:
        import getpass

        EscalationStore(Path(a.root) / "escalation.sqlite3").acknowledge(
            a.ack_incident, getpass.getuser(), now=datetime.now(timezone.utc)
        )
        print("Local operator acknowledgement recorded; no trading authority changed.")
        raise SystemExit(0)
    if a.review_decision:
        from operational_model_review import record

        record(
            a.root,
            a.review_decision,
            a.reason,
            strategy=a.strategy,
            candidate_version=a.candidate_version,
        )
        print("Review request recorded; no freeze, refit or promotion applied.")
        raise SystemExit(0)
    r = run(a.root, a.configuration)
    print(
        json.dumps(
            dict(
                status=r["status"],
                signals=r["signals"],
                external_delivery_verified=False,
            ),
            indent=2,
        )
    )
