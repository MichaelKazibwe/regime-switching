"""Build pinned OpenSSL LTS with official QUIC fixes and QUIC excluded.

This is 3.5.9 with explicitly recorded upstream backports, not a claimed 3.5.10
release. No Debian package version is rewritten or scanner finding suppressed.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tarfile
from urllib.request import urlopen

VERSION = '3.5.9'
URL = 'https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz'
SHA256 = '603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a'
PATCHES = {
    '734c6cd7444bdbf589bfec917e47598c1b21ddd3': 'c1726a50d589b2dc289727865c184382c2bd846733ddb139427062713ebeb5bd',
    'f3acb0a3328046741479482c51cec815839e1b05': 'd52a6af23bc966daaa9eded816a392d429a67bb76faafd922f4c4cf35a9349f4',
}


def verified(data, digest):
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Official OpenSSL input checksum mismatch')
    return data


def download(url, digest, limit):
    with urlopen(url, timeout=120) as response:
        return verified(response.read(limit), digest)


def main():
    archive = Path('/tmp/openssl-source.tar.gz')
    archive.write_bytes(download(URL, SHA256, 64*1024*1024))
    with tarfile.open(archive) as source:
        source.extractall('/tmp', filter='data')
    directory = Path('/tmp/openssl-'+VERSION)
    for commit, digest in PATCHES.items():
        patch = download('https://github.com/openssl/openssl/commit/'+commit+'.patch', digest, 1024*1024)
        subprocess.run(['patch','-p1','--fuzz=0','--batch'], input=patch,
                       cwd=directory, check=True, timeout=60)
    configure = ['./Configure','--prefix=/usr/local','--libdir=lib',
                 '--openssldir=/etc/ssl','shared','no-quic']
    for command in (configure, ['make','-j2'], ['make','install_sw']):
        subprocess.run(command, cwd=directory, check=True, timeout=1200)
    environment = {**os.environ, 'LD_LIBRARY_PATH':'/usr/local/lib'}
    subprocess.run([sys.executable,'deploy/runtime/verify_native_tls.py'],
                   check=True, env=environment, timeout=60)
    receipt = Path('/usr/local/share/regime/openssl-build.json')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(dict(version=VERSION, source=URL, sha256=SHA256,
        upstream_backports=PATCHES, configure=configure,
        source_kind='OFFICIAL_LTS_RELEASE_WITH_CHECKSUM_PINNED_UPSTREAM_BACKPORTS',
        quic_included=False, tls_12_13_verified=True), sort_keys=True))
    license_target = receipt.parent/'licenses/openssl'
    license_target.mkdir(parents=True, exist_ok=True)
    (license_target/'LICENSE.txt').write_bytes((directory/'LICENSE.txt').read_bytes())


if __name__ == '__main__':
    main()
