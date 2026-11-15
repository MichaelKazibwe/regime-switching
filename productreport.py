"""Private local portfolio report with interactive scenario charts; no network."""

import os
from pathlib import Path
import tempfile


def private_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, delete=False, encoding="utf-8"
    ) as handle:
        handle.write(content)
        temporary = handle.name
    os.replace(temporary, path)
    path.chmod(0o600)


def render_report(result, destination):
    """Render the shared investor interface for a single private saved plan."""
    from investor_dashboard import render_dashboard

    render_dashboard([result], destination)
