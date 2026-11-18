# Minimal application runtime

The final application image uses digest-pinned Google distroless Debian 13 cc, CPython 3.12 and the existing hash-locked numerical dependencies. Build tools, shells, OS administration utilities and package installers are not required at runtime. Browser QA uses a separate image with its own browser/OS tools.

SQLite 3.54.1 is compiled from the official release after checking its published SHA3-256. The original vulnerable Debian SQLite library is not copied into the final image. `sqlite-build.json` records its origin and checksum; runtime acceptance must confirm the actual linked SQLite version. Debian dependency metadata is preserved beside every copied OS library so the vulnerability scanner retains package coverage. No CVE ignore list or severity threshold reduction is used.

Unused interactive-terminal, GUI and hardware-UUID CPython extensions are excluded: `_curses`, `_curses_panel`, `readline`, `_tkinter`, `_uuid`. Standard UUID generation uses Python's fallback. Desktop/terminal UI libraries are outside this web/batch application contract. App, numerical, auth, PDF, publication and recovery checks must pass in the exact final image.

Official references:
- https://github.com/GoogleContainerTools/distroless
- https://www.sqlite.org/download.html
- https://www.sqlite.org/releaselog/3_54_1.html

A clean scan is one release requirement. It does not approve investment use, data rights or remote exposure.
