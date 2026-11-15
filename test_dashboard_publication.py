from types import SimpleNamespace
import json

from strategy_dashboard_server import Application


def test_invalid_publication_keeps_previous_financial_state(tmp_path):
    app = object.__new__(Application)
    app.document = tmp_path / "old.html"
    app.payload = {"training": {"run_id": "previous"}}
    app.live_pointer = tmp_path / "latest.json"
    candidate = tmp_path / "new.html"
    candidate.write_text("tampered")
    app.live_pointer.write_text(
        json.dumps(dict(document=str(candidate), document_sha256="invalid"))
    )
    app.refresh()
    assert app.payload["training"]["run_id"] == "previous"
    assert app.document == tmp_path / "old.html"
    assert app.refresh_error


def test_refresh_replaces_complete_application_state(tmp_path, monkeypatch):
    import strategy_dashboard_server as server
    from strategy_integrity import file_hash

    app = object.__new__(Application)
    app.document = tmp_path / "old.html"
    app.output = tmp_path / "pdfs"
    app.live_pointer = tmp_path / "latest.json"
    document = tmp_path / "new.html"
    document.write_text("verified by candidate constructor")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(dict(capture="capture", training_report="report")))
    app.live_pointer.write_text(
        json.dumps(
            dict(
                document=str(document),
                document_sha256=file_hash(document),
                bundle=str(bundle),
                bundle_sha256=file_hash(bundle),
            )
        )
    )
    candidate = SimpleNamespace(
        document=document,
        dashboard_root=tmp_path,
        payload={"new": True},
        lab={"fresh": True},
        results={"new-id": {}},
    )
    monkeypatch.setattr(server, "Application", lambda *args: candidate)
    app.refresh()
    assert app.payload == {"new": True} and app.lab == {"fresh": True}
    assert app.results == {"new-id": {}} and app.refresh_error is None
