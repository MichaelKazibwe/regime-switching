"""Compare rendered tables and all saved exports with the authenticated payload."""

import argparse
import csv
import io
import json
from pathlib import Path

from pilot_browser_test import local_service
from strategy_receipts import atomic_json


def audit(origin, output):
    from playwright.sync_api import sync_playwright, expect

    root = Path(output)
    root.mkdir(exist_ok=False, parents=True)
    evidence = {}

    def percentage(text, value, digits=2):
        if value is None:
            assert text == "Unavailable", text
        else:
            tolerance = .5 * 10 ** (-digits) / 100 + 1e-9
            assert abs(float(text.replace("%", "").replace(",", "")) / 100 - value) <= tolerance, (text, value)

    with sync_playwright() as playwright:
        for engine in ["chromium", "webkit"]:
            browser = getattr(playwright, engine).launch(headless=True)
            context = browser.new_context(accept_downloads=True, locale="en-US")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(origin + "/login")
            page.get_by_label("Username", exact=True).fill("alice@example.test")
            page.get_by_label("Password", exact=True).fill("Synthetic-test-password-123!")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator("#pilot-account")).to_contain_text("alice@example.test", timeout=90000)
            payload = page.request.get(origin + "/api/dashboard").json()
            count, downloads = 0, 0
            for i, plan in enumerate(payload["plans"]):
                page.locator('[data-view="portfolio"]').click()
                page.locator("#profile").select_option(str(i))
                page.locator("#core-only").uncheck()
                page.locator("#capital").fill("250000")
                expect(page.locator("#snapshot-date")).to_have_text(plan["price_session"])
                for row in page.locator("#asset-rows tr").all():
                    symbol = row.locator("button").inner_text()
                    cells = row.locator("td").all_inner_texts()
                    percentage(cells[2], plan["allocation"]["weights"].get(symbol, 0))
                    percentage(cells[3], plan["allocation"]["variance_contributions"].get(symbol))
                    assert cells[5] == "$" + format(payload["latest_market"]["instruments"][symbol]["close"], ".2f")
                    count += 3
                for button, suffix in [("download-csv", "csv"), ("download-plan", "json"), ("download-pdf", "pdf")]:
                    with page.expect_download() as event:
                        page.locator("#" + button).click()
                    path = root / f"{engine}-profile-{i}.{suffix}"
                    event.value.save_as(path)
                    if suffix == "csv":
                        rows = list(csv.DictReader(io.StringIO(path.read_text())))
                        assert abs(sum(float(r["Capital weight"]) for r in rows) - 1) < 1e-8
                        assert all(r["Currency"] == plan["mandate"]["base_currency"] for r in rows)
                        assert all(abs(float(r["Illustrative value"]) - float(r["Capital weight"]) * 250000) < 1e-6 for r in rows)
                    elif suffix == "json":
                        value = json.loads(path.read_text())
                        assert value["plan"]["id"] == plan["id"] and value["illustrative_amount"] == 250000
                    else:
                        assert path.read_bytes().startswith(b"%PDF-")
                    downloads += 1
            page.locator('[data-view="engines"]').click()
            for row in payload["return_engines"]["assessment"]["strategies"]:
                page.locator("#engine-selector").select_option(row["name"])
                a = row["candidate"]
                for tr in page.locator("#engine-weights tr").all():
                    symbol, weight, risk = tr.locator("td").all_inner_texts()
                    percentage(weight, a["cash"] if symbol == "USD_CASH" else a["weights"].get(symbol, 0), digits=1)
                    percentage(risk, 0 if symbol == "USD_CASH" else a["risk_shares"].get(symbol), digits=1)
                    count += 2
            page.locator('[data-view="dynamic"]').click()
            for tr in page.locator("#dynamic-weights tr").all():
                symbol, _, weight, risk = tr.locator("td").all_inner_texts()
                a = payload["dynamic_portfolio"]["snapshot"]
                percentage(weight, a["cash"] if symbol == "USD_CASH" else a["weights"].get(symbol, 0))
                percentage(risk, 0 if symbol == "USD_CASH" else a["risk_shares"].get(symbol, 0))
                count += 2
            with page.expect_download() as event:
                page.locator("#dynamic-pdf").click()
            path = root / f"{engine}-dynamic.pdf"
            event.value.save_as(path)
            assert path.read_bytes().startswith(b"%PDF-")
            downloads += 1
            page.locator('[data-view="macro"]').click()
            for strategy in payload["allocation_lab"]["results"]:
                page.locator("#lab-strategy").select_option(strategy)
                with page.expect_download() as event:
                    page.locator("#lab-pdf").click()
                path = root / f"{engine}-{strategy}.pdf"
                event.value.save_as(path)
                assert path.read_bytes().startswith(b"%PDF-")
                downloads += 1
            assert not errors, errors
            evidence[engine] = dict(rendered_value_comparisons=count, downloads_verified=downloads,
                                    profiles=len(payload["plans"]), page_errors=errors)
            context.close()
            browser.close()
    result = dict(status="PASSED_RENDERED_VALUE_AND_EXPORT_AUDIT", engines=evidence)
    atomic_json(root / "acceptance.json", result)
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    origin = "http://127.0.0.1:8781"
    with local_service(args.snapshot, args.benchmark, args.output, origin):
        audit(origin, args.output)
