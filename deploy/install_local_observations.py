"""Install the reviewed user LaunchAgent; run with explicit filesystem approval."""

import os
from pathlib import Path
import subprocess
from render_launch_agent import render

root = Path(__file__).resolve().parent.parent
for label in (
    "com.regime.live-observations",
    "com.regime.observation-watchdog",
    "com.regime.p1-research",
    "com.regime.live-p1-monitor",
):
    source = root / "deploy" / (label + ".plist")
    rendered = render(source, root)
    target = Path.home() / "Library/LaunchAgents" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != rendered:
        raise SystemExit("Existing different LaunchAgent requires review")
    target.write_bytes(rendered)
    target.chmod(0o600)
    domain = f"gui/{os.getuid()}"
    existing = subprocess.run(
        ["launchctl", "print", f"{domain}/{label}"], capture_output=True
    )
    if existing.returncode != 0:
        subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
    subprocess.run(["launchctl", "print", f"{domain}/{label}"], check=True)
