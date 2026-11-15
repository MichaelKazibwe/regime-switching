"""
test_phase5c_logging_audit.py
=============================
Phase 5C regression tests.
"""

from __future__ import annotations

import json
import logging

import pytest

from audittrail import OperationalAuditTrail
from operationalevent import (
    OperationalEvent,
    OperationalSeverity,
    OperationalSource,
    OperationalEventType,
)
from structuredlogging import OperationalJSONFormatter, OperationalLogger


def make_event(message: str = "test event") -> OperationalEvent:
    return OperationalEvent.create(
        event_type=OperationalEventType.SYSTEM_START,
        severity=OperationalSeverity.INFO,
        source=OperationalSource.SYSTEM,
        message=message,
    )


def test_audit_append_and_read(tmp_path):
    trail = OperationalAuditTrail(tmp_path / "audit.jsonl")
    event = make_event()

    record = trail.append(event)

    assert record.sequence == 1
    assert record.event["event_id"] == event.event_id
    assert trail.count() == 1
    assert trail.read()[0] == record


def test_audit_hash_chain(tmp_path):
    trail = OperationalAuditTrail(tmp_path / "audit.jsonl")

    trail.append(make_event("one"))
    trail.append(make_event("two"))
    trail.append(make_event("three"))

    result = trail.verify()

    assert result["healthy"] is True
    assert result["records"] == 3
    assert len(result["last_hash"]) == 64


def test_audit_survives_restart(tmp_path):
    path = tmp_path / "audit.jsonl"

    first = OperationalAuditTrail(path)
    first.append(make_event("one"))
    first.append(make_event("two"))

    second = OperationalAuditTrail(path)

    assert second.count() == 2
    assert second.verify()["healthy"] is True

    second.append(make_event("three"))
    assert second.count() == 3
    assert second.verify()["healthy"] is True


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    trail = OperationalAuditTrail(path)
    trail.append(make_event())

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["event"]["message"] = "tampered"
    path.write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="integrity failure"):
        OperationalAuditTrail(path)


def test_audit_rejects_non_event(tmp_path):
    trail = OperationalAuditTrail(tmp_path / "audit.jsonl")

    with pytest.raises(TypeError):
        trail.append("not an event")  # type: ignore[arg-type]


def test_structured_formatter():
    event = make_event("structured message")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=event.message,
        args=(),
        exc_info=None,
    )
    record.operational_event = event

    payload = json.loads(
        OperationalJSONFormatter().format(record)
    )

    assert payload["event_id"] == event.event_id
    assert payload["message"] == "structured message"
    assert payload["severity"] == OperationalSeverity.INFO


def test_operational_logger_emits_event(caplog):
    event = make_event("logged")

    logger = logging.getLogger("phase5c.test")
    adapter = OperationalLogger(logger)

    with caplog.at_level(logging.INFO, logger="phase5c.test"):
        adapter.emit(event)

    assert "logged" in caplog.text


def test_module_health_and_metadata(tmp_path):
    trail = OperationalAuditTrail(tmp_path / "audit.jsonl")
    logger = OperationalLogger()

    assert trail.metadata()["api_version"] == "1.0.0"
    assert logger.metadata()["api_version"] == "1.0.0"
    assert trail.health_check()["healthy"] is True
    assert logger.health_check()["healthy"] is True


def test_public_methods_are_side_effect_limited(tmp_path):
    trail = OperationalAuditTrail(tmp_path / "audit.jsonl")
    assert "append" in trail.metadata()["public_methods"]
    assert trail.metadata()["execution_side_effects"] is False
