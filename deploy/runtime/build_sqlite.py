"""Build the checksum-pinned official SQLite security release for CPython."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
from urllib.request import urlopen

VERSION = '3.54.1'
URL = 'https://www.sqlite.org/2026/sqlite-autoconf-3540100.tar.gz'
SHA3 = 'b6ced585c750916b1052667239a12c25a7ff34e7f06e1e6e01ecb0427657d9c4'


def verified_source(data):
    if hashlib.sha3_256(data).hexdigest() != SHA3:
        raise ValueError('Official SQLite source checksum mismatch')
    return data


def main():
    with urlopen(URL, timeout=60) as response:
        data = verified_source(response.read(16 * 1024 * 1024))
    archive = Path('/tmp/sqlite-source.tar.gz')
    archive.write_bytes(data)
    with tarfile.open(archive) as source:
        source.extractall('/tmp', filter='data')
    directory = Path('/tmp/sqlite-autoconf-3540100')
    for command in [['./configure', '--prefix=/usr/local', '--disable-readline'], ['make', '-j2'], ['make', 'install']]:
        subprocess.run(command, cwd=directory, check=True, timeout=600)
    receipt = Path('/usr/local/share/regime/sqlite-build.json')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(dict(version=VERSION, source=URL, sha3_256=SHA3,
        configure=['--prefix=/usr/local', '--disable-readline'], source_kind='OFFICIAL_UPSTREAM_RELEASE'), sort_keys=True))


if __name__ == '__main__':
    main()
