"""Real-browser frontend acceptance for disposable local QA accounts only."""

import argparse
import csv
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

from strategy_integrity import file_hash, strict_json
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
            if os.environ.get("PILOT_REQUIRE_DAILY") == "1":
                page.clock.install()
            errors = []
            benchmark_requests = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: benchmark_requests.append(request.url) if request.url.endswith('/api/benchmark') else None)
            page.set_default_timeout(30000)
            def navigate(section):
                groups = {'decision-home':'home', 'weekly':'portfolios', 'dynamic':'portfolios',
                          'growth':'portfolios', 'proposal-analysis':'analysis', 'benchmark':'analysis',
                          'macro':'analysis', 'news':'intelligence', 'overview':'research',
                          'portfolio':'research', 'engines':'research', 'performance':'research', 'risk':'research'}
                page.locator(f'[data-hub="{groups[section]}"]').click()
                page.locator(f'[data-view="{section}"]').click()
            page.goto(origin + "/login")
            expect(page.get_by_role("heading", name="Sign in", exact=True)).to_be_visible()
            page.get_by_label("Username", exact=True).fill("alice@example.test")
            page.get_by_label("Password", exact=True).fill("Synthetic-test-password-123!")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator('#workspace-search')).to_be_visible(timeout=90000)
            expect(page.locator("#pilot-account")).to_contain_text("alice@example.test", timeout=90000)
            if os.environ.get("PILOT_REQUIRE_DAILY") == "1":
                navigate('weekly')
                def daily_status(route):
                    route.fulfill(json=dict(version="synthetic-new-daily-run", market_session="2026-11-13", stale=False, error=None))
                    page.unroute('**/api/dashboard-status', daily_status)
                page.route('**/api/dashboard-status', daily_status)
                with page.expect_navigation(wait_until='domcontentloaded'):
                    page.clock.fast_forward(60000)
                expect(page.locator('#pilot-account')).to_contain_text('alice@example.test', timeout=90000)
                expect(page.locator('[data-panel="weekly"]')).to_be_visible()
            if os.environ.get('PILOT_REQUIRE_MACRO_ALPHA') == '1':
                navigate('macro')
                alpha = page.request.get(origin + '/api/macro-alpha').json()
                expect(page.locator('#macro-alpha-global')).to_contain_text('stale snapshot' if alpha['stale'] else 'testing', timeout=30000)
                f = alpha['forecast']
                assert f['monitoring_enabled'] and not f['portfolio_activation_enabled'] and not f['execution_enabled']
                assert abs(sum(f['prediction']['probabilities']) - 1) < 1e-9
                assert set(f['components']).isdisjoint(f['missing_components'])
                for path in ['/api/dashboard', '/api/benchmark', '/api/observations', '/api/weekly']:
                    assert page.request.get(origin + path).json()['macro_alpha']['forecast']['forecast_id'] == f['forecast_id']
                page.locator('#macro-alpha-global').click()
                expect(page.locator('#macro-alpha-panel')).to_be_visible()
                expect(page.locator('#macro-alpha-probabilities tr')).to_have_count(4)
                expect(page.locator('#macro-alpha-inputs tr')).to_have_count(4)
                expect(page.locator('#macro-alpha-outcomes')).to_contain_text('pending' if alpha.get('monitoring') else 'Prospective receipt unavailable')
            sections = page.locator("[data-view]").evaluate_all("nodes=>nodes.map(n=>n.dataset.view)")
            visited = []
            navigation_ms = []
            for section in sections:
                started = time.perf_counter()
                navigate(section)
                expect(page.locator(f'[data-panel="{section}"]')).to_be_visible()
                navigation_ms.append(round((time.perf_counter() - started) * 1000, 2))
                expect(page.locator("#page-title")).not_to_have_text("")
                visited.append(section)
            if os.environ.get("PILOT_REQUIRE_WORKSPACE") == "1":
                navigate('decision-home')
                expect(page.locator('#decision-title')).not_to_have_text('Current proposal')
                current = page.request.get(origin + '/api/workspace').json()
                assert not current['execution_enabled']
                for key, portfolio in current['portfolios'].items():
                    page.locator('#decision-portfolio').select_option(key)
                    expect(page.locator('#decision-title')).to_have_text(portfolio['title'])
                    expect(page.locator('#decision-dates')).to_contain_text(portfolio['context']['price_as_of'])
                    expect(page.locator('#decision-metrics .decision-metric').first.locator('strong')).to_have_text(str(portfolio['asset_count']))
                    assert page.locator('[data-panel="decision-home"]').get_attribute('data-context-id') == portfolio['context']['context_id']
                    page.locator('#decision-analyze').click()
                    expect(page.locator('[data-panel="proposal-analysis"]')).to_be_visible()
                    assert page.locator('[data-panel="proposal-analysis"]').get_attribute('data-context-id') == portfolio['context']['context_id']
                    for period in ('4','13','52','156'):
                        page.locator('#decision-period').select_option(period)
                        scenario = portfolio['projections']['periods'][period]
                        expected = ' / '.join(f"{scenario[k]*100:.2f}%" for k in ('p05_return','median_return','p95_return'))
                        expect(page.locator('#decision-projection .decision-metric').first.locator('strong')).to_have_text(expected)
                    page.locator('#decision-analysis-home').click()
                page.screenshot(path=str(root / f'{name}-decision-home.png'), full_page=True)
                page.locator('#decision-review').click()
                expect(page.locator('[data-panel="weekly"]')).to_be_visible()
                expect(page.locator('#weekly-horizon')).to_have_value(key)
                page.set_viewport_size(dict(width=390,height=844))
                navigate('decision-home')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(root / f'{name}-decision-mobile.png'), full_page=True)
                if os.environ.get('PILOT_REQUIRE_DAILY') == '1':
                    retained_context = page.locator('[data-panel="decision-home"]').get_attribute('data-context-id')
                    def unavailable_workspace(route):
                        route.fulfill(status=503, json={'error':'Synthetic update failure'})
                    page.route('**/api/workspace', unavailable_workspace)
                    page.clock.fast_forward(61000)
                    expect(page.locator('#decision-status')).to_contain_text('retaining the last verified proposal')
                    assert page.locator('[data-panel="decision-home"]').get_attribute('data-context-id') == retained_context
                    page.unroute('**/api/workspace', unavailable_workspace)
                    page.clock.fast_forward(61000)
                    expect(page.locator('#decision-status')).not_to_contain_text('Update failed')
                page.set_viewport_size(dict(width=1440,height=1000))
            if os.environ.get("PILOT_REQUIRE_WEEKLY") == "1":
                navigate('weekly')
                expect(page.locator('#weekly-status')).to_contain_text('Week closed')
                weekly = page.request.get(origin + '/api/weekly').json()
                for key in ('short', 'medium', 'long', 'aggregate'):
                    page.locator('#weekly-horizon').select_option(key)
                    rows = weekly['candidates'][key]['allocations']
                    expect(page.locator('#weekly-holdings tr')).to_have_count(len(rows))
                    for index, row in enumerate(rows):
                        cells = page.locator('#weekly-holdings tr').nth(index).locator('td')
                        expect(cells.nth(0)).to_have_text(row['symbol'])
                        expect(cells.nth(1)).to_have_text(f"{row['weight'] * 100:.2f}%")
                    expect(page.locator('#weekly-projections tr')).to_have_count(4)
                    median = weekly['candidates'][key]['projections']['52']['median_return']
                    expect(page.locator('#weekly-projections tr').nth(2).locator('td').nth(2)).to_have_text(f'{median * 100:.2f}%')
                expect(page.locator('#weekly-comparison tr')).to_have_count(4)
                expect(page.locator('#weekly-strategy-mix')).to_contain_text('Data-optimized')
                for sleeve, weight in weekly['candidates']['aggregate']['strategy_mix'].items():
                    expect(page.locator('#weekly-strategy-mix')).to_contain_text(f'{weight * 100:.2f}%')
                page.locator('#weekly-capital').fill('200000')
                expect(page.locator('#weekly-projections tr').nth(2).locator('td').nth(4)).to_have_text(f'${200000 * (1 + median):,.0f}')
                page.route('**/api/weekly', lambda route: route.fulfill(status=503, json={'error':'Unavailable QA refresh'}))
                page.evaluate('()=>{window.qaOriginalNow=Date.now;Date.now=()=>window.qaOriginalNow()+61001;}')
                page.locator('#weekly-capital').fill('200001')
                expect(page.locator('#weekly-status')).to_contain_text('Refresh failed · retained published snapshot')
                expect(page.locator('#weekly-holdings tr')).to_have_count(len(weekly['candidates']['aggregate']['allocations']))
                page.unroute('**/api/weekly')
                page.locator('#weekly-capital').fill('200000')
                expect(page.locator('#weekly-status')).not_to_contain_text('Refresh failed')
                page.evaluate('()=>{Date.now=window.qaOriginalNow;delete window.qaOriginalNow;}')
                with page.expect_download() as event:
                    page.locator('#weekly-pdf').click()
                event.value.save_as(root / f'{name}-weekly.pdf')
                assert (root / f'{name}-weekly.pdf').read_bytes().startswith(b'%PDF-')
                page.screenshot(path=str(root / f'{name}-weekly-desktop.png'), full_page=True)
                page.set_viewport_size(dict(width=390, height=844))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(root / f'{name}-weekly-mobile.png'), full_page=True)
                page.set_viewport_size(dict(width=1440, height=1000))
            navigate('benchmark')
            if os.environ.get('PILOT_REQUIRE_RESEARCH_REVIEW') == '1':
                navigate('weekly')
                page.locator('#weekly-review-rationale').fill('Synthetic reviewer requests validation of risk assumptions')
                page.locator('#weekly-review-submit').click()
                expect(page.locator('#weekly-review-status')).to_contain_text('Recorded',timeout=30000)
            if os.environ.get("PILOT_REQUIRE_MACRO_MONITOR") == "1":
                navigate('macro')
                expect(page.locator('#macro-monitor-status')).to_contain_text('Market session', timeout=90000)
                monitor = page.request.get(origin + '/api/macro-monitor').json()
                assert monitor['execution_enabled'] is False
                for quarter in monitor['quarters']:
                    page.locator('#macro-monitor-quarter').select_option(quarter['quarter'])
                    rows = [r for r in monitor['rows'] if r['quarter'] == quarter['quarter']]
                    expect(page.locator('#macro-monitor-daily tr')).to_have_count(len(rows))
                    expect(page.locator('#macro-monitor-daily tr').first.locator('td').first).to_have_text(rows[-1]['date'])
                    actual = page.locator('#macro-monitor-quarterly tr').filter(has=page.get_by_role('button', name=quarter['quarter'], exact=True))
                    mean = quarter['daily_context_means']['CPIAUCSL']
                    expect(actual.locator('td').nth(5)).to_have_text(f'{mean:.2f}' if mean is not None else 'Unavailable')
                    daily_cpi = rows[-1]['series']['CPIAUCSL']['value']
                    expect(page.locator('#macro-monitor-daily tr').first.locator('td').nth(3)).to_contain_text(f'{daily_cpi:.2f}' if daily_cpi is not None else 'Unavailable')
                page.locator('#macro-monitor-quarter').select_option(monitor['quarters'][0]['quarter'])
                assert not page.locator('.macro-monitor-archive').evaluate('node=>node.open')
                with page.expect_download() as event:
                    page.locator('#macro-monitor-csv').click()
                event.value.save_as(root / f'{name}-daily-macro.csv')
                with (root / f'{name}-daily-macro.csv').open() as stream:
                    exported = list(csv.reader(stream))
                assert len(exported) - 1 == monitor['quarters'][0]['observed_sessions']
                page.screenshot(path=str(root / f'{name}-macro-desktop.png'), full_page=True)
                page.set_viewport_size(dict(width=390, height=844))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(root / f'{name}-macro-mobile.png'), full_page=True)
                page.set_viewport_size(dict(width=1440, height=1000))
                navigate('benchmark')
            expect(page.locator("#benchmark-note")).to_contain_text("Research reference", timeout=90000)
            expect(page.locator("#portfolio-identity")).to_contain_text("Cycle-diversified")
            expect(page.locator("#benchmark-weights tr")).to_have_count(len(page.request.get(origin + "/api/benchmark").json()["latest"]["weights"]) + 1)
            for option in page.locator("#benchmark-scenario option").evaluate_all("nodes=>nodes.map(n=>n.value)"):
                page.locator("#benchmark-scenario").select_option(option)
                expect(page.locator("#benchmark-scenario-note")).to_contain_text("Conditional one-year")
            with page.expect_download() as event:
                page.locator("#benchmark-download").click()
            download = event.value
            download.save_as(root / f"{name}-benchmark.json")
            report = json.loads((root / f"{name}-benchmark.json").read_text())
            assert report["execution_enabled"] is False
            assert page.locator('[data-hub]').count() == 5
            assert set(sections) == {'decision-home','proposal-analysis','weekly','dynamic','growth','benchmark','macro','news','overview','portfolio','engines','performance','risk'}
            fixed_allocation = page.locator('#benchmark-weights tr').evaluate_all(
                "rows=>rows.map(r=>[...r.cells].slice(0,3).map(c=>c.textContent))")
            medians = set()
            for scenario_name, scenario in report['scenarios'].items():
                page.locator('#benchmark-scenario').select_option(scenario_name)
                for metric, key in [('median', 'median_return'), ('downside', 'p05_return'),
                                    ('upside', 'p95_return'), ('drawdown', 'p95_drawdown'),
                                    ('loss', 'probability_loss_10pct')]:
                    expected = page.evaluate("v=>new Intl.NumberFormat(undefined,{style:'percent',maximumFractionDigits:1}).format(v)", scenario[key])
                    expect(page.locator(f'#benchmark-metrics [data-metric="{metric}"] strong')).to_have_text(expected)
                medians.add(page.locator('#benchmark-metrics [data-metric="median"] strong').inner_text())
            assert len(medians) > 1
            assert fixed_allocation == page.locator('#benchmark-weights tr').evaluate_all(
                "rows=>rows.map(r=>[...r.cells].slice(0,3).map(c=>c.textContent))")
            page.locator('#benchmark-capital').fill('200000')
            last_scenario = list(report['scenarios'].values())[-1]
            expected = page.evaluate("v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(v)", 200000 * (1 + last_scenario['median_return']))
            expect(page.locator('#benchmark-metrics [data-metric="ending"] strong')).to_have_text(expected)
            page.locator('#benchmark-compare').select_option(next(iter(report['scenarios'])))
            expect(page.locator('#benchmark-comparison')).to_contain_text('percentage points')
            page.locator('#benchmark-mode-return').click()
            expect(page.locator('#benchmark-mode-return')).to_have_attribute('aria-pressed', 'true')
            page.locator('#benchmark-chart').focus()
            page.keyboard.press('ArrowRight')
            expect(page.locator('#benchmark-crosshair')).to_contain_text('Month')
            with page.expect_download() as comparison_download:
                page.locator('#benchmark-comparison-download').click()
            comparison_path = root / f'{name}-comparison.csv'
            comparison_download.value.save_as(comparison_path)
            with comparison_path.open() as stream:
                comparison_rows = list(csv.DictReader(stream))
            assert len(comparison_rows) == 2
            assert float(comparison_rows[0]['Median return']) == last_scenario['median_return']
            assert float(comparison_rows[0]['Illustration USD']) == 200000
            page.locator('.brand').click()
            expect(page.locator('[data-panel="overview"]')).to_be_visible()
            page.locator('#workspace-search').click()
            page.locator('#workspace-search-input').fill('risk')
            page.locator('.command-result').first.click()
            expect(page.locator('[data-panel="risk"]')).to_be_visible()
            for merged in ['observations', 'assumptions']:
                page.locator(f'[data-merged="{merged}"] > summary').click()
                expect(page.locator(f'[data-merged="{merged}"]')).to_have_attribute('open', '')
            navigate('benchmark')
            page.screenshot(path=str(root / f"{name}-benchmark-desktop.png"), full_page=True)
            navigate('portfolio')
            page.locator("#asset-search").fill("SPY")
            expect(page.locator("#asset-rows")).to_contain_text("SPY")
            page.locator("#asset-search").fill("NO-SUCH-ASSET")
            expect(page.locator("#asset-rows")).to_contain_text("No instruments match")
            page.locator("#asset-search").fill("")
            navigate('overview')
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
                navigate(section)
                expect(page.locator(f'[data-panel="{section}"]')).to_be_visible()
                if not page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"):
                    overflow = page.evaluate("""()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,
                      elements:[...document.querySelectorAll('main *')].map(n=>({id:n.id,tag:n.tagName,
                      cls:typeof n.className==='string'?n.className:'',right:n.getBoundingClientRect().right,
                      width:n.getBoundingClientRect().width})).filter(n=>n.width>0&&n.right>innerWidth+2).slice(0,40)})""")
                    atomic_json(root / f"{name}-{section}-overflow.json", overflow)
                    page.screenshot(path=str(root / f"{name}-{section}-overflow.png"), full_page=True)
                    raise AssertionError("Mobile overflow: " + section)
            navigate("benchmark")
            expect(page.locator('[data-panel="benchmark"]')).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            assert page.locator('#benchmark-chart').bounding_box()['height'] >= 240
            assert page.locator('.market-tile strong').evaluate_all('nodes=>nodes.every(n=>n.scrollWidth<=n.clientWidth+1)')
            page.screenshot(path=str(root / f"{name}-benchmark-mobile.png"), full_page=True)
            navigate("macro")
            expect(page.locator("#lab-strategy")).to_be_visible()
            for i in range(4):
                page.locator(f"#lab-prob-{i}").fill("25")
            try:
                expect(page.locator("#lab-preset")).to_have_value("custom", timeout=90000)
            except AssertionError as error:
                raise AssertionError(page.locator('#lab-status').inner_text()) from error
            with page.expect_download() as event:
                with page.expect_response(lambda response: response.url.endswith('/api/scenario-pdf')) as pdf_response:
                    page.locator("#lab-pdf").click()
                response = pdf_response.value
                assert response.status == 200, dict(status=response.status, error=response.text(), lab_status=page.locator('#lab-status').inner_text())
            event.value.save_as(root / f"{name}-scenario.pdf")
            assert (root / f"{name}-scenario.pdf").read_bytes().startswith(b"%PDF-")
            page.locator("#pilot-logout").click()
            expect(page).to_have_url(origin + "/login")
            assert page.request.get(origin + "/api/dashboard").status == 401
            page.get_by_label("Username", exact=True).fill("viewer@example.test")
            page.get_by_label("Password", exact=True).fill("Synthetic-test-password-123!")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator("#workspace-search")).to_be_visible(timeout=90000)
            navigate("macro")
            expect(page.locator("#lab-prob-0")).to_be_disabled()
            expect(page.locator("#lab-quarters")).to_be_disabled()
            if os.environ.get('PILOT_REQUIRE_RESEARCH_REVIEW') == '1':
                expect(page.locator('#weekly-review-submit')).to_be_disabled()
            page.locator("#pilot-logout").click()
            expect(page).to_have_url(origin + "/login")
            assert not errors, errors
            assert len(benchmark_requests) == 1
            evidence[name] = dict(sections=visited, viewport_desktop=[1440, 1000], viewport_mobile=[390, 844],
                                  benchmark_scenarios=len(report["scenarios"]), page_errors=errors,
                                  logout_revoked=True, viewer_controls_disabled=True,
                                  scenario_metric_cases=len(report['scenarios']),
                                  grouped_navigation=True, command_search=True,
                                  fixed_reference_preserved=True, illustration_scaling=True,
                                  tester_navigation_ms=navigation_ms, benchmark_fetches=len(benchmark_requests),
                                  benchmark_download_sha256=file_hash(root / f"{name}-benchmark.json"))
            atomic_json(root / f"{name}-acceptance.json", dict(status="PASSED_ENGINE_ACCEPTANCE", **evidence[name]))
            context.close()
            browser.close()
    receipt = dict(status="PASSED_BROWSER_ACCEPTANCE", checked_at=datetime.now(timezone.utc).isoformat(),
                   browsers=evidence, execution_enabled=False,
                   source_hashes={p: file_hash(p) for p in ["pilot_server.py", "pilot_auth.py", "pilot_browser_test.py",
                                                           "pilot/bootstrap.js", "pilot/login.js", "pilot/benchmark.js", "pilot/pilot.css",
                                                           "pilot/workspace.js", "pilot/weekly.js", "pilot/macro-monitor.js",
                                                           "portfolio_workspace.py", "pilot/decision-workspace.js",
                                                           "pilot/decision-workspace.html", "pilot/decision-workspace.css",
                                                           "pilot/weekly.html", "pilot/macro-monitor.html", "dashboard/investor.js",
                                                           "dashboard/investor.html", "dashboard/investor.css"]})
    if Path('pilot-release.json').is_file():
        release = strict_json('pilot-release.json')
        receipt['source_release_id'] = release['release_id']
        receipt['source_commit'] = release['source_commit']
    receipt['image_digest'] = os.environ.get('PILOT_QA_IMAGE_DIGEST')
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
