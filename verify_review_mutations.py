"""Targeted adversarial regression checks; mutated code runs only in temporary copies."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile

from strategy_integrity import file_hash
from strategy_receipts import atomic_json


def run(output):
    root = Path(__file__).resolve().parent
    cases = [
        (
            "future_fx",
            "global_market_panel.py",
            " & (rates.session <= valuation_date)",
            "",
            "test_global_market_panel.py::test_new_availability_does_not_legitimize_future_or_obsolete_fx",
        ),
        (
            "missing_reference",
            "cycle_benchmark.py",
            'if missing:\n        raise ValueError("Missing declared benchmark holdings: " + ", ".join(sorted(missing)))',
            "if missing:\n        pass",
            "test_cycle_benchmark.py::test_reference_never_silently_drops_holdings_or_accepts_invalid_weights",
        ),
    ]
    results = []
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, module, before, after, test in cases:
        source = (root / module).read_text()
        if before not in source:
            raise ValueError("Mutation specification no longer matches " + module)
        with tempfile.TemporaryDirectory(prefix="regime-mutant-") as tmp:
            target = Path(tmp) / module
            mutated = source.replace(before, after, 1)
            if name == "future_fx":
                release_guard = 'if chosen.available_at.tz_convert("UTC").tz_localize(None).normalize() < chosen.session:'
                if release_guard not in mutated:
                    raise ValueError("Release-order guard mutation no longer matches")
                mutated = mutated.replace(release_guard, "if False:", 1)
            target.write_text(mutated)
            env = {
                **os.environ,
                "PYTHONPATH": str(tmp) + os.pathsep + str(root),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "--import-mode=importlib",
                    "-q",
                    str(root / test.split("::")[0]) + "::" + test.split("::")[1],
                ],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            (output / (name + ".log")).write_text(completed.stdout + completed.stderr)
            results.append(
                dict(
                    mutation=name,
                    module=module,
                    original_sha256=file_hash(root / module),
                    killed_by_regression=completed.returncode == 1,
                    exit_code=completed.returncode,
                )
            )
    receipt = dict(
        status="PASSED_TARGETED_MUTATION_CHECKS"
        if all(r["killed_by_regression"] for r in results)
        else "FAILED",
        mutations=results,
        scope="Two specific financial correctness faults; not a whole-project mutation score",
    )
    atomic_json(output / "receipt.json", receipt)
    if receipt["status"] == "FAILED":
        raise ValueError("An adversarial mutation escaped or failed to execute")
    return receipt


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    print(run(p.parse_args().output))
