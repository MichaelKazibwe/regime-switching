"""Real-browser frontend acceptance for disposable local QA accounts only."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from strategy_integrity import file_hash
from strategy_receipts import atomic_json


@contextmanager
def local_service(snapshot, benchmark, output, origin):
    from pilot_auth import AuthStore

    parsed = urlsplit(origin)
    if parsed.hostname != "127.0.0.1" or parsed.scheme != "http" or parsed.username or not parsed.port:
        raise ValueError("Disposable QA service must be loopback only")
    state = Path(str(Path(output).resolve()) + "-state")
    if state.exists():
        raise ValueError("Use a unique disposable QA state directory")
    store = AuthStore(state / "auth.sqlite3")
    for username, role in [("alice@example.test", "tester"), ("bob@example.test", "tester"),
                           ("viewer@example.test", "viewer")]:
        store.add_user(username, "Synthetic-test-password-123!", role=role, must_change=False)
    with (state / "server.log").open("w") as log:
        command = [sys.executable, "pilot_server.py", "--snapshot", str(Path(snapshot).resolve()),
                   "--state", str(state), "--origin", origin, "--port", str(parsed.port), "--insecure-local"]
        if benchmark:
            command += ["--benchmark", str(Path(benchmark).resolve())]
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError("Disposable QA service failed; inspect its private server log")
                try:
                    with urlopen(origin + "/healthz", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Disposable QA service did not become alive")
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run(origin, output, *, browsers=("chromium", "firefox", "webkit")):
    from playwright.sync_api import sync_playwright, expect

    if not origin.startswith("http://127.0.0.1:"):
        raise ValueError("This disposable-credential test driver is for loopback QA only")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    # Firefox on macOS needs canonical temp/cache paths rather than /var or /tmp aliases.
    temporary = Path(tempfile.gettempdir()).resolve() / "regime-pilot-browser-tmp"
    temporary.mkdir(exist_ok=True, mode=0o700)
    os.environ["TMPDIR"] = str(temporary)
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]).resolve())
    evidence = {}
    with sync_playwright() as playwright:
        for name in browsers:
            browser = getattr(playwright, name).launch(headless=True)
            context = browser.new_context(viewport=dict(width=1440, height=1000), accept_downloads=True,
                                          reduced_motion="reduce")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_default_timeout(30000)
            page.goto(origin + "/login")
            expect(page.get_by_role("heading", name="Sign in", exact=True)).to_be_visible()
            page.get_by_label("Username", exact=True).fill("alice@example.test")
            page.get_by_label("Password", exact=True).fill("Synthetic-test-password-123!")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator('[data-view="growth"]')).to_be_visible(timeout=90000)
            expect(page.locator("#pilot-account")).to_contain_text("alice@example.test", timeout=90000)
            sections = page.locator("[data-view]").evaluate_all("nodes=>nodes.map(n=>n.dataset.view)")
            visited = []
            for section in sections:
                page.locator(f'[data-view="{section}"]').click()
                expect(page.locator(f'[data-panel="{section}"]')).to_be_visible()
                expect(page.locator("#page-title")).not_to_have_text("")
                visited.append(section)
            expect(page.locator("#benchmark-note")).to_contain_text("Research reference", timeout=90000)
            expect(page.locator("#portfolio-identity")).to_contain_text("Cycle-diversified")
            expect(page.locator("#benchmark-weights tr")).to_have_count(28)
            for option in page.locator("#benchmark-scenario option").evaluate_all("nodes=>nodes.map(n=>n.value)"):
                page.locator("#benchmark-scenario").select_option(option)
                expect(page.locator("#benchmark-scenario-note")).to_contain_text("Conditional one-year")
            with page.expect_download() as event:
                page.locator("#benchmark-download").click()
            download = event.value
            download.save_as(root / f"{name}-benchmark.json")
            report = json.loads((root / f"{name}-benchmark.json").read_text())
            assert report["execution_enabled"] is False
            page.screenshot(path=str(root / f"{name}-benchmark-desktop.png"), full_page=True)
            page.locator('[data-view="portfolio"]').click()
            page.locator("#asset-search").fill("SPY")
            expect(page.locator("#asset-rows")).to_contain_text("SPY")
            page.locator("#asset-search").fill("NO-SUCH-ASSET")
            expect(page.locator("#asset-rows")).to_contain_text("No instruments match")
            page.locator("#asset-search").fill("")
            page.locator('[data-view="overview"]').click()
            median_before = page.locator("#median-value").inner_text()
            page.locator("#capital").fill("250000")
            page.locator("#capital").dispatch_event("change")
            expect(page.locator("#capital")).to_have_value("250000")
            expect(page.locator("#median-value")).not_to_have_text(median_before)
            with page.expect_download() as event:
                page.locator("#download-pdf").click()
            event.value.save_as(root / f"{name}-saved-plan.pdf")
            assert (root / f"{name}-saved-plan.pdf").read_bytes().startswith(b"%PDF-")
            page.get_by_role("button", name="Night mode").click()
            expect(page.locator("body")).to_have_class(__import__("re").compile("night"))
            page.screenshot(path=str(root / f"{name}-overview-night.png"), full_page=True)
            page.get_by_role("button", name="Day mode").click()
            page.set_viewport_size(dict(width=390, height=844))
            for section in sections:
                page.locator("#section-jump").select_option(section)
                expect(page.locator(f'[data-panel="{section}"]')).to_be_visible()
                if not page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"):
                    overflow = page.evaluate("""()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,
                      elements:[...document.querySelectorAll('main *')].map(n=>({id:n.id,tag:n.tagName,
                      cls:typeof n.className==='string'?n.className:'',right:n.getBoundingClientRect().right,
                      width:n.getBoundingClientRect().width})).filter(n=>n.width>0&&n.right>innerWidth+2).slice(0,40)})""")
                    atomic_json(root / f"{name}-{section}-overflow.json", overflow)
                    page.screenshot(path=str(root / f"{name}-{section}-overflow.png"), full_page=True)
                    raise AssertionError("Mobile overflow: " + section)
            page.locator("#section-jump").select_option("benchmark")
            expect(page.locator('[data-panel="benchmark"]')).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            page.screenshot(path=str(root / f"{name}-benchmark-mobile.png"), full_page=True)
            page.locator("#section-jump").select_option("macro")
            expect(page.locator("#lab-strategy")).to_be_visible()
            for i in range(4):
                page.locator(f"#lab-prob-{i}").fill("25")
            expect(page.locator("#lab-preset")).to_have_value("custom", timeout=90000)
            with page.expect_download() as event:
                page.locator("#lab-pdf").click()
            event.value.save_as(root / f"{name}-scenario.pdf")
            assert (root / f"{name}-scenario.pdf").read_bytes().startswith(b"%PDF-")
            page.locator("#pilot-logout").click()
            expect(page).to_have_url(origin + "/login")
            assert page.request.get(origin + "/api/dashboard").status == 401
            page.get_by_label("Username", exact=True).fill("viewer@example.test")
            page.get_by_label("Password", exact=True).fill("Synthetic-test-password-123!")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator("#section-jump")).to_be_visible(timeout=90000)
            page.locator("#section-jump").select_option("macro")
            expect(page.locator("#lab-prob-0")).to_be_disabled()
            expect(page.locator("#lab-quarters")).to_be_disabled()
            page.locator("#pilot-logout").click()
            expect(page).to_have_url(origin + "/login")
            assert not errors, errors
            evidence[name] = dict(sections=visited, viewport_desktop=[1440, 1000], viewport_mobile=[390, 844],
                                  benchmark_scenarios=len(report["scenarios"]), page_errors=errors,
                                  logout_revoked=True, viewer_controls_disabled=True,
                                  benchmark_download_sha256=file_hash(root / f"{name}-benchmark.json"))
            atomic_json(root / f"{name}-acceptance.json", dict(status="PASSED_ENGINE_ACCEPTANCE", **evidence[name]))
            context.close()
            browser.close()
    receipt = dict(status="PASSED_BROWSER_ACCEPTANCE", checked_at=datetime.now(timezone.utc).isoformat(),
                   browsers=evidence, execution_enabled=False,
                   source_hashes={p: file_hash(p) for p in ["pilot_server.py", "pilot_auth.py", "pilot_browser_test.py",
                                                           "pilot/bootstrap.js", "pilot/login.js", "pilot/benchmark.js", "pilot/pilot.css"]})
    atomic_json(root / "acceptance.json", receipt)
    print(json.dumps(dict(status=receipt["status"], browsers=list(evidence))))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8780")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browsers", nargs="+", default=["chromium", "firefox", "webkit"])
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--benchmark", type=Path)
    args = parser.parse_args()
    if args.snapshot:
        with local_service(args.snapshot, args.benchmark, args.output, args.origin):
            run(args.origin, args.output, browsers=tuple(args.browsers))
    else:
        run(args.origin, args.output, browsers=tuple(args.browsers))
