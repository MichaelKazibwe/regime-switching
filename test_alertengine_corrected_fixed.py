"""

Phase 5F — Alert / Notification Engine Regression Tests



Tests:

- Alert policy behavior

- Severity and event-type matching

- Notification transport behavior

- Successful delivery

- Delivery failure

- Duplicate-event suppression

- Non-alert suppression

- Notification result serialization

- Engine serialization

- Health checks

- Metadata and summary

- Immutability

- Operational event compatibility

- Execution-layer isolation



Phase: 5F

API version: 1.0.0

"""



from __future__ import annotations



from dataclasses import FrozenInstanceError



import pytest



from alertengine import (

    AlertConfigurationError,

    AlertEngine,

    AlertEngineError,

    AlertEventError,

    AlertPolicy,

    AlertStatus,

    InMemoryNotificationTransport,

    NotificationChannel,

    NotificationDeliveryError,

    NotificationResult,

)

from operationalevent import (

    OperationalEvent,

    OperationalEventType,

    OperationalSeverity,

    OperationalSource,

)





# ---------------------------------------------------------------------------

# Helpers

# ---------------------------------------------------------------------------

def build_event(

    *,

    event_id: str = "EVENT-001",

    event_type: str = OperationalEventType.RISK_LIMIT_BREACH,

    severity: str = OperationalSeverity.WARNING,

    source: str = OperationalSource.RISK,

    message: str = "Risk limit breached.",

    decision_id: str | None = "DECISION-001",

    order_id: str | None = None,

    execution_id: str | None = None,

    fill_id: str | None = None,

    regime: str | None = "EXPANSION",

) -> OperationalEvent:

    return OperationalEvent(

        event_id=event_id,

        event_type=event_type,

        severity=severity,

        source=source,

        timestamp="2026-01-01T12:00:00+00:00",

        message=message,

        decision_id=decision_id,

        order_id=order_id,

        execution_id=execution_id,

        fill_id=fill_id,

        regime=regime,

        metadata={"test": True},

    )





def build_engine(

    *,

    policy: AlertPolicy | None = None,

    transport: InMemoryNotificationTransport | None = None,

    default_recipient: str = "test@example.com",

) -> tuple[AlertEngine, InMemoryNotificationTransport]:

    actual_transport = transport or InMemoryNotificationTransport()



    engine = AlertEngine(

        policy=policy,

        transport=actual_transport,

        default_recipient=default_recipient,

    )



    return engine, actual_transport





# ---------------------------------------------------------------------------

# Constants / API

# ---------------------------------------------------------------------------





def test_api_version():

    assert AlertEngine.API_VERSION == "1.0.0"





def test_phase():

    assert AlertEngine.PHASE == "5F"





def test_component():

    assert AlertEngine.COMPONENT == "AlertEngine"





def test_notification_channel():

    assert NotificationChannel.EMAIL == "EMAIL"





def test_alert_status_constants():

    assert AlertStatus.SENT == "SENT"

    assert AlertStatus.FAILED == "FAILED"

    assert AlertStatus.SUPPRESSED == "SUPPRESSED"





# ---------------------------------------------------------------------------

# AlertPolicy

# ---------------------------------------------------------------------------





def test_default_policy_alerts_warning_events():

    policy = AlertPolicy()



    event = build_event(

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.WARNING,

    )



    assert policy.should_alert(event) is True





def test_default_policy_alerts_error_events():

    policy = AlertPolicy()



    event = build_event(

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.ERROR,

    )



    assert policy.should_alert(event) is True





def test_default_policy_alerts_critical_events():

    policy = AlertPolicy()



    event = build_event(

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.CRITICAL,

    )



    assert policy.should_alert(event) is True





def test_default_policy_suppresses_info_event_when_not_explicitly_configured():

    policy = AlertPolicy()



    event = build_event(

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.INFO,

    )



    assert policy.should_alert(event) is False





def test_explicit_event_type_can_trigger_alert():

    policy = AlertPolicy(
       alert_severities=(OperationalSeverity.WARNING,),
       alert_event_types=(OperationalEventType.AUDIT,),
    )



    event = build_event(

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.INFO,

    )



    assert policy.should_alert(event) is True





def test_unconfigured_info_event_is_suppressed():

    policy = AlertPolicy()



    event = build_event(

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.INFO,

    )



    assert policy.should_alert(event) is False





def test_policy_is_immutable():

    policy = AlertPolicy()



    with pytest.raises(FrozenInstanceError):

        policy.alert_severities = frozenset()





# ---------------------------------------------------------------------------

# Transport

# ---------------------------------------------------------------------------





def test_in_memory_transport_has_email_channel():

    transport = InMemoryNotificationTransport()



    assert transport.channel == NotificationChannel.EMAIL





def test_in_memory_transport_records_successful_delivery():

    transport = InMemoryNotificationTransport()



    event = build_event(event_id="EVENT-001")

    result = transport.send(
       notification_id="ALERT-001",
       event=event,
       recipient="test@example.com",
    )



    assert result.status == AlertStatus.SENT

    assert result.notification_id == "ALERT-001"

    assert result.recipient == "test@example.com"

    assert len(transport.sent_notifications) == 1





def test_in_memory_transport_can_simulate_delivery_failure():

    transport = InMemoryNotificationTransport(fail_delivery=True)



    event = build_event(event_id="EVENT-001")

    result = transport.send(
       notification_id="ALERT-001",
       event=event,
       recipient="test@example.com",
    )



    assert result.status == AlertStatus.FAILED

    assert result.notification_id == "ALERT-001"

    assert len(transport.sent_notifications) == 1
    assert transport.sent_notifications[0].status == AlertStatus.FAILED





def test_transport_failure_flag_can_be_configured():
    transport = InMemoryNotificationTransport()

    transport.fail_delivery = True

    assert transport.fail_delivery is True





# ---------------------------------------------------------------------------

# AlertEngine configuration

# ---------------------------------------------------------------------------





def test_engine_requires_valid_transport():

    class InvalidTransport:

        pass



    with pytest.raises(AlertConfigurationError):

        AlertEngine(transport=InvalidTransport())





def test_engine_accepts_valid_transport():

    transport = InMemoryNotificationTransport()



    engine = AlertEngine(transport=transport)



    assert engine.health_check()["healthy"] is True





def test_default_recipient_is_preserved():

    engine, _ = build_engine(

        default_recipient="alerts@example.com"

    )



    assert engine.default_recipient == "alerts@example.com"





# ---------------------------------------------------------------------------

# Alert processing

# ---------------------------------------------------------------------------





def test_warning_event_is_sent():

    engine, transport = build_engine()



    event = build_event(

        severity=OperationalSeverity.WARNING,

    )



    result = engine.process(event)



    assert result.status == AlertStatus.SENT

    assert result.notification_id == "ALERT-EVENT-001"

    assert result.recipient == "test@example.com"

    assert len(transport.sent_notifications) == 1





def test_critical_event_is_sent():

    engine, transport = build_engine()



    event = build_event(

        event_id="EVENT-CRITICAL",

        severity=OperationalSeverity.CRITICAL,

    )



    result = engine.process(event)



    assert result.status == AlertStatus.SENT

    assert result.notification_id == "ALERT-EVENT-CRITICAL"

    assert len(transport.sent_notifications) == 1





def test_info_event_is_suppressed():

    engine, transport = build_engine()



    event = build_event(

        event_id="EVENT-INFO",

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.INFO,

    )



    result = engine.process(event)



    assert result.status == AlertStatus.SUPPRESSED

    assert result.notification_id == "ALERT-EVENT-INFO"

    assert len(transport.sent_notifications) == 1
    assert transport.sent_notifications[0].status == AlertStatus.FAILED





def test_duplicate_event_is_suppressed():

    engine, transport = build_engine()



    event = build_event(

        event_id="EVENT-DUPLICATE",

        severity=OperationalSeverity.CRITICAL,

    )



    first = engine.process(event)

    second = engine.process(event)



    assert first.status == AlertStatus.SENT

    assert second.status == AlertStatus.SUPPRESSED

    assert len(transport.sent_notifications) == 1





def test_alert_alias_behaves_like_process():

    engine, transport = build_engine()



    event = build_event(

        event_id="EVENT-ALIAS",

        severity=OperationalSeverity.WARNING,

    )



    result = engine.alert(event)



    assert result.status == AlertStatus.SENT

    assert len(transport.sent_notifications) == 1





# ---------------------------------------------------------------------------

# Explicit operational events

# ---------------------------------------------------------------------------





@pytest.mark.parametrize(

    "event_type",

    [

        OperationalEventType.KILL_SWITCH_ACTIVATED,

        OperationalEventType.CIRCUIT_BREAKER_OPENED,

        OperationalEventType.EXECUTION_REJECTED,

        OperationalEventType.EXECUTION_FAILED,

        OperationalEventType.MARKET_DATA_STALE,

        OperationalEventType.MARKET_DATA_INVALID,

        OperationalEventType.RISK_LIMIT_BREACH,

        OperationalEventType.RECONCILIATION_DISCREPANCY,

        OperationalEventType.HEALTH_FAILED,

    ],

)

def test_default_policy_alerts_configured_operational_event_types(event_type):

    engine, transport = build_engine()



    event = build_event(

        event_id=f"EVENT-{event_type}",

        event_type=event_type,

        severity=OperationalSeverity.INFO,

    )



    result = engine.process(event)



    assert result.status == AlertStatus.SENT

    assert len(transport.sent_notifications) == 1





# ---------------------------------------------------------------------------

# Failed delivery

# ---------------------------------------------------------------------------





def test_failed_delivery_returns_failed_result():

    transport = InMemoryNotificationTransport(

        fail_delivery=True

    )



    engine, _ = build_engine(

        transport=transport,

    )



    event = build_event(

        event_id="EVENT-FAILED",

        severity=OperationalSeverity.CRITICAL,

    )



    result = engine.process(event)



    assert result.status == AlertStatus.FAILED

    assert result.notification_id == "ALERT-EVENT-FAILED"





# ---------------------------------------------------------------------------

# NotificationResult

# ---------------------------------------------------------------------------





def test_notification_result_serialization_round_trip():

    result = NotificationResult(
       notification_id="ALERT-001",
       event_id="EVENT-001",
       status=AlertStatus.SENT,
       channel=NotificationChannel.EMAIL,
       attempted=True,
       delivered=True,
       recipient="test@example.com",
       error=None,
    )



    data = result.to_dict()



    restored = NotificationResult.from_dict(data)



    assert restored == result





def test_notification_result_is_immutable():

    result = NotificationResult(
       notification_id="ALERT-001",
       event_id="EVENT-001",
       status=AlertStatus.SENT,
       channel=NotificationChannel.EMAIL,
       attempted=True,
       delivered=True,
       recipient="test@example.com",
       error=None,
    )



    with pytest.raises(FrozenInstanceError):

        result.status = AlertStatus.FAILED





def test_notification_result_health_check():

    result = NotificationResult(
       notification_id="ALERT-001",
       event_id="EVENT-001",
       status=AlertStatus.SENT,
       channel=NotificationChannel.EMAIL,
       attempted=True,
       delivered=True,
       recipient="test@example.com",
       error=None,
    )



    health = result.health_check()



    assert health["healthy"] is True





# ---------------------------------------------------------------------------

# Engine counters / state

# ---------------------------------------------------------------------------





def test_engine_tracks_sent_count():

    engine, _ = build_engine()



    event = build_event(

        event_id="EVENT-SENT",

        severity=OperationalSeverity.WARNING,

    )



    engine.process(event)



    summary = engine.summary()



    assert summary["alert_count"] == 1





def test_engine_tracks_suppressed_count():

    engine, _ = build_engine()



    event = build_event(

        event_id="EVENT-SUPPRESS",

        event_type=OperationalEventType.AUDIT,

        severity=OperationalSeverity.INFO,

    )



    engine.process(event)



    summary = engine.summary()



    assert summary["suppressed_count"] == 1





def test_engine_tracks_duplicate_as_suppressed():

    engine, _ = build_engine()



    event = build_event(

        event_id="EVENT-DUP",

        severity=OperationalSeverity.WARNING,

    )



    engine.process(event)

    engine.process(event)



    summary = engine.summary()



    assert summary["alert_count"] == 1

    assert summary["suppressed_count"] == 1





def test_engine_tracks_failed_count():

    transport = InMemoryNotificationTransport(

        fail_delivery=True

    )



    engine, _ = build_engine(

        transport=transport,

    )



    event = build_event(

        event_id="EVENT-FAIL",

        severity=OperationalSeverity.CRITICAL,

    )



    engine.process(event)



    summary = engine.summary()



    assert summary["failed_count"] == 1





# ---------------------------------------------------------------------------

# Health / metadata

# ---------------------------------------------------------------------------





def test_engine_health_check_is_healthy():

    engine, _ = build_engine()



    health = engine.health_check()



    assert health["healthy"] is True

    assert health["component"] == "AlertEngine"





def test_engine_metadata_contains_api_information():

    engine, _ = build_engine()



    metadata = engine.metadata()



    assert metadata["api_version"] == "1.0.0"

    assert metadata["phase"] == "5F"

    assert metadata["component"] == "AlertEngine"





def test_engine_summary_contains_required_fields():

    engine, _ = build_engine()



    summary = engine.summary()



    required = {

        "sent_count",

        "failed_count",

        "suppressed_count",

    }



    assert required.issubset(summary.keys())





# ---------------------------------------------------------------------------

# Engine serialization

# ---------------------------------------------------------------------------





def test_engine_to_dict_contains_api_version():

    engine, _ = build_engine()



    data = engine.to_dict()



    assert data["api_version"] == "1.0.0"





def test_engine_to_dict_contains_phase():

    engine, _ = build_engine()



    data = engine.to_dict()



    assert data["phase"] == "5F"





def test_engine_to_dict_contains_component():

    engine, _ = build_engine()



    data = engine.to_dict()



    assert data["component"] == "AlertEngine"





# ---------------------------------------------------------------------------

# OperationalEvent compatibility

# ---------------------------------------------------------------------------





def test_operational_event_round_trip():

    event = build_event(

        event_id="EVENT-ROUNDTRIP",

        severity=OperationalSeverity.ERROR,

    )



    data = event.to_dict()

    restored = OperationalEvent.from_dict(data)



    assert restored == event





def test_alert_engine_preserves_event_identity():

    engine, transport = build_engine()



    event = build_event(

        event_id="EVENT-IDENTITY",

        severity=OperationalSeverity.CRITICAL,

    )



    result = engine.process(event)



    assert result.notification_id == "ALERT-EVENT-IDENTITY"

    assert transport.sent_notifications[0].notification_id == (
       "ALERT-EVENT-IDENTITY"
    )





# ---------------------------------------------------------------------------

# Error hierarchy

# ---------------------------------------------------------------------------





def test_alert_engine_error_hierarchy():

    assert issubclass(

        AlertConfigurationError,

        AlertEngineError,

    )



    assert issubclass(

        AlertEventError,

        AlertEngineError,

    )



    assert issubclass(

        NotificationDeliveryError,

        AlertEngineError,

    )





# ---------------------------------------------------------------------------

# Execution isolation

# ---------------------------------------------------------------------------





def test_alert_engine_has_no_execution_authorization_api():

    engine, _ = build_engine()



    forbidden = {

        "authorize",

        "require_authorization",

        "submit_order",

        "route_order",

        "execute_order",

        "create_order",

    }



    for method_name in forbidden:

        assert not hasattr(engine, method_name)





def test_alert_engine_does_not_mutate_operational_event():

    engine, _ = build_engine()



    event = build_event(

        event_id="EVENT-IMMUTABLE",

        severity=OperationalSeverity.WARNING,

    )



    before = event.to_dict()



    engine.process(event)



    after = event.to_dict()



    assert after == before





# ---------------------------------------------------------------------------

# Final regression marker

# ---------------------------------------------------------------------------





def test_phase5f_regression_contract():

    engine, transport = build_engine()



    event = build_event(

        event_id="FINAL-5F",

        severity=OperationalSeverity.CRITICAL,

    )



    result = engine.process(event)



    assert result.status == AlertStatus.SENT

    assert len(transport.sent_notifications) == 1



    health = engine.health_check()



    assert health["healthy"] is True



    summary = engine.summary()



    assert summary["alert_count"] == 1





if __name__ == "__main__":

    pytest.main([__file__, "-v"])
