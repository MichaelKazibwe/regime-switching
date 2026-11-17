"""Isolated synthetic optimizer capacity measurements; no market-performance claim."""

from pathlib import Path
import copy
import json
import os
import subprocess
import sys
import tempfile
import time

from global_asset_registry import load_registry
from strategy_receipts import atomic_json


def run(output, counts=(100, 500)):
    rows = []
    for count in counts:
        registry = load_registry().payload()
        registry["schema_version"] = 1
        registry["instruments"] = [
            i for i in registry["instruments"] if i["research_enabled"]
        ]
        prototype = next(i for i in registry["instruments"] if i["symbol"] == "MSFT")
        while len(registry["instruments"]) < count:
            row = copy.deepcopy(prototype)
            row.update(
                symbol=f"QA{len(registry['instruments']):05}",
                provider_symbol="SYNTHETIC",
                sources=["Synthetic capacity fixture, not market data"],
            )
            registry["instruments"].append(row)
        with tempfile.TemporaryDirectory(prefix="regime-capacity-") as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry))
            script = """
import json,time,resource,sys
import numpy as np,pandas as pd
from global_asset_registry import load_registry
from weekly_portfolios import allocate,POLICIES
symbols=load_registry().symbols()
rng=np.random.default_rng(20261117)
history=pd.DataFrame(rng.normal(.001,.015,(156,len(symbols))),columns=symbols)
started=time.perf_counter();w,cov,mu=allocate(history,POLICIES['medium'])
assert np.isfinite(w).all() and w.min()>=0 and w.max()<=.20+1e-7 and w.sum()<=.95+1e-7
print(json.dumps(dict(assets=len(symbols),seconds=time.perf_counter()-started,max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),allocation_constraints_passed=True)))
"""
            started = time.perf_counter()
            try:
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    env={
                        **os.environ,
                        "REGIME_UNIVERSE_CONFIG": str(path),
                        "OPENBLAS_NUM_THREADS": "1",
                        "OMP_NUM_THREADS": "1",
                    },
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if result.returncode:
                    rows.append(
                        dict(assets=count, status="FAILED", error=result.stderr[-1500:])
                    )
                else:
                    rows.append(
                        dict(
                            status="MEASURED_SYNTHETIC_CAPACITY",
                            **json.loads(result.stdout),
                        )
                    )
            except subprocess.TimeoutExpired:
                rows.append(
                    dict(
                        assets=count,
                        status="TIME_BUDGET_EXCEEDED",
                        seconds=time.perf_counter() - started,
                    )
                )
    receipt = dict(
        status="CAPACITY_MEASUREMENTS",
        results=rows,
        synthetic_fixture=True,
        target_hardware_qualified=False,
        financial_performance_claim=False,
    )
    atomic_json(output, receipt)
    return receipt


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(p.parse_args().output), indent=2))
