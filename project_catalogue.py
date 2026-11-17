"""Generate a current source/capability map; static reachability is not deletion authority."""

import ast
from pathlib import Path
from collections import Counter

from strategy_integrity import file_hash
from strategy_receipts import atomic_json


def catalogue(root):
    root = Path(root)
    modules = {p.stem: p for p in root.glob("*.py")}
    rows = []
    for name, path in sorted(modules.items()):
        source = path.read_text()
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(n.name.split(".")[0] for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        role = (
            "test"
            if name.startswith("test_") or name.endswith("_test")
            else "runtime_or_research"
        )
        if name in {"rewrite", "regression_suite_r3b"}:
            role = "compatibility_or_historical_tool"
        rows.append(
            dict(
                module=path.name,
                role=role,
                lines=len(source.splitlines()),
                sha256=file_hash(path),
                local_imports=sorted(imports & set(modules)),
                entrypoint=any(
                    isinstance(n, ast.If) and "__name__" in ast.unparse(n.test)
                    for n in tree.body
                ),
                description=(ast.get_docstring(tree) or "").split("\n")[0],
                owner="UNASSIGNED",
            )
        )
    return dict(
        schema_version=1,
        modules=rows,
        role_counts=dict(Counter(r["role"] for r in rows)),
        limitations="Static imports do not prove runtime use or disuse. Explicit ownership and capability qualification require human review.",
    )


def write(root, output):
    data = catalogue(root)
    output = Path(output)
    atomic_json(output.with_suffix(".json"), data)
    lines = [
        "# Current project module catalogue",
        "",
        "Generated from current source. Historical phase documents are preserved separately.",
        "Owner UNASSIGNED is explicit; this generator does not invent responsibility or deployment approval.",
        "",
        "| Module | Role | Lines | CLI entry | Description |",
        "|---|---|---:|---|---|",
    ]
    for r in data["modules"]:
        lines.append(
            "| "
            + r["module"]
            + " | "
            + r["role"]
            + " | "
            + str(r["lines"])
            + " | "
            + str(r["entrypoint"])
            + " | "
            + r["description"].replace("|", "/")
            + " |"
        )
    output.write_text("\n".join(lines) + "\n")
    return data


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = write(args.root, args.output)
    print(result["role_counts"])
