"""Exercise the actual CPython-linked TLS library without external networks."""
import ctypes
from pathlib import Path
import ssl
import re
import subprocess
import tempfile


def verify():
    if not ssl.OPENSSL_VERSION.startswith('OpenSSL 3.5.9 '):
        raise ValueError('Pinned CPython-linked OpenSSL required')
    configuration = Path('/usr/local/include/openssl/configuration.h').read_text()
    if not re.search(r'^\s*#\s*define\s+OPENSSL_NO_QUIC\s*$', configuration, re.MULTILINE):
        raise ValueError('QUIC must be excluded from the built library')
    library = ctypes.CDLL('libssl.so.3')
    if hasattr(library, 'OSSL_QUIC_client_method'):
        raise ValueError('Excluded QUIC entry point remains available')
    if not ssl.create_default_context().cert_store_stats()['x509_ca']:
        raise ValueError('System TLS trust anchors are missing')
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        key, cert = root/'key.pem', root/'cert.pem'
        subprocess.run(['/usr/local/bin/openssl','req','-config','/dev/null','-x509','-newkey','rsa:2048',
                        '-nodes','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
                        '-days','1','-keyout',str(key),'-out',str(cert)],
                       check=True, capture_output=True, timeout=30)
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server.load_cert_chain(cert,key)
            client = ssl.create_default_context(cafile=str(cert))
            for context in (client,server):
                context.minimum_version = context.maximum_version = version
            ci, co, si, so = (ssl.MemoryBIO() for _ in range(4))
            c = client.wrap_bio(ci,co,server_hostname='localhost')
            s = server.wrap_bio(si,so,server_side=True)
            completed = set()
            for _ in range(100):
                for name, endpoint in (('client',c),('server',s)):
                    if name not in completed:
                        try:
                            endpoint.do_handshake()
                            completed.add(name)
                        except ssl.SSLWantReadError:
                            pass
                if co.pending:
                    si.write(co.read())
                if so.pending:
                    ci.write(so.read())
                if len(completed) == 2:
                    break
            if len(completed) != 2:
                raise ValueError('Trusted local TLS handshake did not complete')
            c.write(b'qualified-runtime-tls')
            si.write(co.read())
            if s.read() != b'qualified-runtime-tls':
                raise ValueError('TLS application data mismatch')
            print('Verified trusted local handshake and application data:',c.version())


if __name__ == '__main__':
    verify()
