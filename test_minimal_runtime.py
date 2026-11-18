"""Native packaging must reject missing links and corrupted upstream inputs."""
import pytest
from deploy.runtime.collect_runtime import dependencies
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
