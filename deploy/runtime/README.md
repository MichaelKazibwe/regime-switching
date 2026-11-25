# Minimal application runtime

The final application image uses digest-pinned Google distroless Debian 13 base-nossl, CPython 3.12 and the existing hash-locked numerical dependencies. Build tools, shells, OS administration utilities and package installers are not required at runtime. Browser QA uses a separate image with its own browser/OS tools.

SQLite 3.54.1 is compiled from the official release after checking its published SHA3-256. The original vulnerable Debian SQLite library is not copied into the final image. `sqlite-build.json` records its origin and checksum; runtime acceptance must confirm the actual linked SQLite version. Debian dependency metadata is preserved beside every copied OS library so the vulnerability scanner retains package coverage. No CVE ignore list or severity threshold reduction is used.

Unused interactive-terminal, GUI and hardware-UUID CPython extensions are excluded: `_curses`, `_curses_panel`, `readline`, `_tkinter`, `_uuid`. Standard UUID generation uses Python's fallback. Desktop/terminal UI libraries are outside this web/batch application contract. App, numerical, auth, PDF, publication and recovery checks must pass in the exact final image.

Official references:
- https://github.com/GoogleContainerTools/distroless
- https://www.sqlite.org/download.html
- https://www.sqlite.org/releaselog/3_54_1.html

A clean scan is one release requirement. It does not approve investment use, data rights or remote exposure.

OpenSSL uses the checksum-pinned official 3.5.9 LTS source plus the exact
upstream fixes for CVE-2026-107494 and CVE-2026-124709. It is labelled as a patched
3.5.9 build, not an unreleased 3.5.10 release. QUIC is also excluded at compile time:
this application requires ordinary TLS. Build qualification checks the actually
linked CPython library, absence of the QUIC entry point, and trusted local TLS 1.2
and TLS 1.3 handshakes with encrypted application data. The runtime retains the
source/patch checksums and upstream license. The original Debian OpenSSL libraries
are omitted only when no copied runtime dependency links them; their metadata is
never deleted to conceal a copied library. A fresh image scan is still required.

- https://openssl-library.org/news/vulnerabilities/
- https://security-tracker.debian.org/tracker/CVE-2026-107494
- https://security-tracker.debian.org/tracker/CVE-2026-124709

The final base explicitly excludes the distribution OpenSSL copy. Only the patched upstream runtime is retained; required GCC/C++ libraries are copied with their own Debian provenance by the dependency collector. Exact-image acceptance verifies that no second system OpenSSL remains.
