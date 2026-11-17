"""Exact-image, recent vulnerability evidence gate; no implicit risk waivers."""

from datetime import datetime, timezone
from pathlib import Path

from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json


def verify(path, image, *, now=None):
    now = now or datetime.now(timezone.utc)
    doc = strict_json(path)
    created = datetime.fromisoformat(doc["CreatedAt"].replace("Z", "+00:00"))
    identities = {doc.get("ArtifactName"), doc.get("Metadata", {}).get("ImageID")}
    identities.update(doc.get("Metadata", {}).get("RepoDigests", []))
    if (
        image not in identities
        or created.tzinfo is None
        or not 0 <= (now - created).total_seconds() <= 86400
    ):
        raise ValueError("Recent evidence bound to the exact image digest required")
    if not isinstance(doc.get("Results"), list) or not doc["Results"]:
        raise ValueError("Nonempty scanner coverage evidence required")
    findings = [
        dict(
            id=v["VulnerabilityID"],
            package=v["PkgName"],
            installed=v["InstalledVersion"],
            fixed=v.get("FixedVersion"),
            severity=v["Severity"],
            target=r.get("Target"),
        )
        for r in doc["Results"]
        for v in r.get("Vulnerabilities", [])
        if v["Severity"] in {"HIGH", "CRITICAL"}
    ]
    return dict(
        status="BLOCKED_SECURITY_FINDINGS"
        if findings
        else "PASSED_IMAGE_VULNERABILITY_GATE",
        image=image,
        scan_sha256=file_hash(path),
        created_at=doc["CreatedAt"],
        findings=findings,
        unresolved_count=len(findings),
        production_approval=False,
        sbom_generated=False,
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--scan", type=Path, required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = verify(args.scan, args.image)
    atomic_json(args.output, result)
    print(result["status"], result["unresolved_count"])
    raise SystemExit(0 if not result["findings"] else 2)
