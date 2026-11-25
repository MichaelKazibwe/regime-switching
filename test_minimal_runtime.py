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
