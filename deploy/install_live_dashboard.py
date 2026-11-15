"""Install the loopback investor viewer as a user login service."""

import os
from pathlib import Path
import subprocess
import plistlib
from render_launch_agent import render

root = Path(__file__).resolve().parent.parent
label = "com.regime.investor-dashboard"
source = root / "deploy" / (label + ".plist")
rendered = render(source, root)
target = Path.home() / "Library/LaunchAgents" / source.name
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists() and target.read_bytes() != rendered:
    old, new = plistlib.loads(target.read_bytes()), plistlib.loads(rendered)
    if (
        old.get("Label") != label
        or old.get("ProgramArguments") != new["ProgramArguments"]
    ):
        raise SystemExit("Existing different dashboard configuration requires review")
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], check=True)
target.write_bytes(rendered)
target.chmod(0o600)
domain = f"gui/{os.getuid()}"
existing = subprocess.run(
    ["launchctl", "print", f"{domain}/{label}"], capture_output=True
)
if existing.returncode:
    subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
subprocess.run(["launchctl", "print", f"{domain}/{label}"], check=True)
