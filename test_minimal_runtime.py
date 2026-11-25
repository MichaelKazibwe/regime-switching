"""Native packaging must reject missing links and corrupted upstream inputs."""
import pytest
from deploy.runtime.collect_runtime import dependencies, copy_native
from deploy.runtime.build_sqlite import verified_source


def test_missing_shared_library_is_a_hard_failure():
    with pytest.raises(ValueError, match='Unresolved'):
        dependencies('libsqlite3.so.0 => not found')


def test_real_ldd_addresses_are_not_library_paths():
    paths = dependencies('linux-vdso.so.1 (0x000f)\nlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x001)\n/lib64/ld-linux-x86-64.so.2 (0x000)')
    assert {str(p) for p in paths} == {'/lib/x86_64-linux-gnu/libc.so.6','/lib64/ld-linux-x86-64.so.2'}


def test_bad_sqlite_source_is_never_compiled():
    with pytest.raises(ValueError, match='checksum mismatch'):
        verified_source(b'corrupted release bytes')


def test_dynamic_loader_retains_execution_permission(tmp_path):
    source = tmp_path/'loader.so'
    source.write_bytes(b'executable-loader-fixture')
    source.chmod(0o755)
    target = copy_native(source, tmp_path/'runtime')
    assert target.stat().st_mode & 0o111 == 0o111
    assert target.read_bytes() == source.read_bytes()


def test_bad_openssl_release_and_patch_are_never_compiled():
    from deploy.runtime.build_openssl import verified
    with pytest.raises(ValueError, match='checksum mismatch'):
        verified(b'corrupted native source', 'a'*64)


def test_snapshot_import_uses_the_same_configured_macro_stream_as_its_forecast(tmp_path,monkeypatch):
    from pilot_release import seed_runtime
    from strategy_receipts import atomic_json
    from strategy_integrity import strict_json,file_hash
    root=tmp_path/'source'
    runtime=tmp_path/'runtime'
    inputs=runtime/'pilot-input'
    atomic_json(inputs/'market/capture.json',dict(macro_manifest='macro-manifest.json',price_session='2026-11-24'))
    atomic_json(inputs/'market/macro-manifest.json',dict(series={}))
    atomic_json(inputs/'snapshot-manifest.json',dict(files={}))
    atomic_json(root/'var/macro-alpha/latest.json',dict(scope='wrong default stream'))
    configured=tmp_path/'configured-monitor'
    atomic_json(configured/'latest.json',dict(scope='configured stream'))
    monkeypatch.setenv('PILOT_MACRO_ALPHA_STATE_ROOT',str(configured))
    seed_runtime(root,runtime,inputs)
    copied=runtime/'macro-alpha/latest.json'
    assert strict_json(copied)['scope']=='configured stream'
    assert file_hash(copied)==file_hash(configured/'latest.json')
    assert strict_json(inputs/'cohort-import.json')['monitoring_streams']['macro-alpha/latest.json']==file_hash(copied)
