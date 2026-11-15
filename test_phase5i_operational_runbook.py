from pathlib import Path


RUNBOOK = Path("OPERATIONAL_RUNBOOK.md")


def test_operational_runbook_exists():
    assert RUNBOOK.is_file(), "OPERATIONAL_RUNBOOK.md must exist"


def test_runbook_documents_normal_startup():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Normal Startup" in text


def test_runbook_documents_normal_shutdown():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Normal Shutdown" in text


def test_runbook_documents_abnormal_restart_and_recovery():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Abnormal Restart" in text
    assert "Recovery Failure" in text


def test_runbook_documents_fail_closed_recovery():
    text = RUNBOOK.read_text(encoding="utf-8").lower()
    assert "fail closed" in text
    assert "execution" in text


def test_runbook_documents_kill_switch_incident():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Kill Switch Incident" in text


def test_runbook_documents_circuit_breaker_incident():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Circuit Breaker Incident" in text


def test_runbook_documents_operational_health_failure():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Operational Health Failure" in text


def test_runbook_documents_alert_and_audit_failure():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Alert" in text
    assert "AuditTrail" in text


def test_runbook_documents_incident_escalation():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Incident Escalation" in text
    assert "human approval" in text.lower()


def test_runbook_preserves_authority_separation():
    text = RUNBOOK.read_text(encoding="utf-8").lower()

    required_concepts = [
        "successful restart",
        "healthy operational status",
        "execution",
        "does not authorize",
    ]

    for concept in required_concepts:
        assert concept in text, (
            f"Runbook must explicitly preserve authority separation: {concept}"
        )
