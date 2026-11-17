"""Test the exact app container using a separate disposable browser container.

No real users, production volumes, public ports or cloud resources are used.
Docker CLI connection settings are inherited from DOCKER_HOST/DOCKER_CONFIG.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid


def run(app_image, browser_image, fixture, output):
    fixture, output = Path(fixture).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("New acceptance output directory required")
    output.mkdir(parents=True, mode=0o700)
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker CLI required")
    prefix = "regime-review-qa-" + uuid.uuid4().hex[:12]
    volumes = {k: prefix + "-" + k for k in ["inputs", "daily", "weekly", "qa"]}
    containers = []

    def command(args, *, timeout=120):
        return subprocess.run(
            [docker, *args], check=True, text=True, capture_output=True, timeout=timeout
        ).stdout.strip()

    try:
        for volume in volumes.values():
            command(["volume", "create", volume])
        seed = prefix + "-seed"
        containers.append(seed)
        command(
            [
                "create",
                "--name",
                seed,
                "--network",
                "none",
                "--user",
                "0:0",
                *sum(
                    (
                        ["--mount", f"type=volume,src={v},dst=/{k}"]
                        for k, v in volumes.items()
                    ),
                    [],
                ),
                "--entrypoint",
                "sh",
                app_image,
                "-c",
                "chown -R 10001:10001 /inputs /daily /weekly /qa",
            ]
        )
        for local, volume in [
            (fixture / "release/runtime", "inputs"),
            (fixture / "daily-published", "daily"),
            (fixture / "weekly-published", "weekly"),
        ]:
            command(["cp", str(local) + "/.", seed + ":/" + volume])
        command(["start", "-a", seed])
        setup = (
            "from pilot_auth import AuthStore; s=AuthStore('/qa/state/auth.sqlite3'); "
            "[(s.add_user(u,'Synthetic-test-password-123!',role=r,must_change=False)) "
            "for u,r in [('alice@example.test','tester'),('bob@example.test','tester'),('viewer@example.test','viewer')]]"
        )
        command(
            [
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--mount",
                f"type=volume,src={volumes['qa']},dst=/qa",
                "--entrypoint",
                "python",
                app_image,
                "-c",
                setup,
            ]
        )
        app = prefix + "-app"
        containers.append(app)
        image_id = command(["image", "inspect", app_image, "--format", "{{.Id}}"])
        mounts = [
            "--mount",
            f"type=volume,src={volumes['inputs']},dst=/app/var,readonly",
            "--mount",
            f"type=volume,src={volumes['daily']},dst=/app/daily-research,readonly",
            "--mount",
            f"type=volume,src={volumes['weekly']},dst=/app/weekly-research/published,readonly",
        ]
        common = [
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "2g",
            "--cpus",
            "2",
            "--pids-limit",
            "256",
            "--tmpfs",
            "/tmp:size=512m,mode=1777",
            *mounts,
            "--mount",
            f"type=volume,src={volumes['qa']},dst=/qa",
            "-e",
            "PILOT_ALLOW_SYNTHETIC_QA=1",
            "-e",
            "PILOT_DAILY_ROOT=/app/daily-research",
            "-e",
            "PILOT_WEEKLY_ROOT=/app/weekly-research/published",
        ]
        command(
            [
                "run",
                "-d",
                "--name",
                app,
                "--network",
                "none",
                *common,
                "--entrypoint",
                "python",
                image_id,
                "pilot_server.py",
                "--snapshot",
                "/app/var/pilot-input/launch.json",
                "--state",
                "/qa/state",
                "--origin",
                "http://127.0.0.1:8781",
                "--port",
                "8781",
                "--bind",
                "127.0.0.1",
                "--insecure-local",
                "--benchmark",
                "/app/var/pilot-input/benchmark.json",
            ]
        )
        for attempt in range(120):
            try:
                command(
                    [
                        "exec",
                        app,
                        "python",
                        "-c",
                        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8781/healthz',timeout=2).read()",
                    ],
                    timeout=10,
                )
                break
            except subprocess.CalledProcessError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Isolated exact-image app failed to start")
        performance_script = r"""
import json,time,urllib.request,http.cookiejar,concurrent.futures,math
origin='http://127.0.0.1:8781'
jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
request=urllib.request.Request(origin+'/api/login',data=json.dumps({'username':'alice@example.test','password':'Synthetic-test-password-123!'}).encode(),headers={'Content-Type':'application/json','Origin':origin})
opener.open(request,timeout=30).read()
cookie='; '.join(c.name+'='+c.value for c in jar)
paths=['/api/dashboard','/api/weekly','/api/benchmark','/api/macro-monitor','/api/observations']
def measure(path):
 start=time.perf_counter()
 with urllib.request.urlopen(urllib.request.Request(origin+path,headers={'Cookie':cookie}),timeout=30) as response:
  payload=response.read();status=response.status;json.loads(payload)
 return {'path':path,'status':status,'seconds':time.perf_counter()-start,'bytes':len(payload)}
cold=[measure(path) for path in paths]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(measure,paths*4))
durations=sorted(r['seconds'] for r in rows);p95=durations[math.ceil(.95*len(durations))-1]
assert all(r['status']==200 and r['bytes']<8*1024*1024 for r in rows)
assert p95<10,'Local invited-group p95 budget exceeded'
print(json.dumps({'status':'PASSED_LOCAL_PILOT_LOAD_BUDGET','workers':4,'requests':len(rows),'warm_p95_seconds':p95,'max_payload_bytes':max(r['bytes'] for r in rows),'cold_endpoint_samples':cold,'samples':rows,'wan_qualified':False,'scope':'Four concurrent local readers; excludes simultaneous optimizer/export load and broad scalability claims'}))
"""
        performance = json.loads(
            command(["exec", app, "python", "-c", performance_script], timeout=120)
        )
        (output / "performance.json").write_text(json.dumps(performance, indent=2))
        browser = prefix + "-browser"
        containers.append(browser)
        flags = sum(
            (
                ["-e", "PILOT_REQUIRE_" + key + "=1"]
                for key in [
                    "MACRO_ALPHA",
                    "MACRO_MONITOR",
                    "WEEKLY",
                    "DAILY",
                    "RESEARCH_REVIEW",
                ]
            ),
            [],
        )
        command(
            [
                "run",
                "--name",
                browser,
                "--network",
                "container:" + app,
                "--shm-size",
                "256m",
                *common,
                *flags,
                "-e",
                "PILOT_QA_IMAGE_DIGEST=" + image_id,
                "--entrypoint",
                "python",
                browser_image,
                "pilot_browser_test.py",
                "--origin",
                "http://127.0.0.1:8781",
                "--output",
                "/qa/browser",
                "--browsers",
                "chromium",
                "webkit",
            ],
            timeout=900,
        )
        command(["cp", seed + ":/qa/browser/.", str(output)])
        receipt = json.loads((output / "acceptance.json").read_text())
        if (
            receipt["image_digest"] != image_id
            or receipt["status"] != "PASSED_BROWSER_ACCEPTANCE"
        ):
            raise ValueError("Exact-image browser receipt mismatch")
        print(
            json.dumps(
                {"status": receipt["status"], "image": image_id, "disposable": True}
            )
        )
    finally:
        for name in containers:
            logs = subprocess.run(
                [docker, "logs", name], capture_output=True, text=True
            )
            (output / (name.rsplit("-", 1)[-1] + ".log")).write_text(
                logs.stdout + logs.stderr
            )
        if containers:
            subprocess.run([docker, "rm", "-f", *containers], capture_output=True)
        for volume in volumes.values():
            subprocess.run([docker, "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-image", required=True)
    parser.add_argument("--browser-image", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.app_image, args.browser_image, args.fixture, args.output)
