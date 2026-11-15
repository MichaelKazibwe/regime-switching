"""Immutable, content-addressed research inputs for exact decision replay."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
import gzip
import hashlib
import importlib.metadata
import json
from collections.abc import Mapping
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np
import pandas as pd


class ResearchArtifactError(RuntimeError):
    """Raised when research evidence is missing, changed, or unreadable."""


class ResearchDataStore:
    """Store exact input envelopes as immutable, SHA-256-addressed artifacts.

    The format is JSON metadata plus IEEE-754 hexadecimal float encoding,
    compressed deterministically with gzip. It never uses pickle or executes
    artifact content while loading.
    """

    API_VERSION = "1.0.0"
    SCHEMA_VERSION = 2
    FORMAT = "regime-switching-research-inputs"
    ROOT = Path(__file__).resolve().parent

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    @staticmethod
    def _float_hex(value: float) -> str:
        return struct.pack(">d", float(value)).hex()

    @classmethod
    def _encode_index(cls, index: pd.Index) -> dict[str, Any]:
        if isinstance(index, pd.DatetimeIndex):
            return {
                "kind": "datetime",
                "name": cls._encode(index.name),
                "timezone": None if index.tz is None else str(index.tz),
                "values": [cls._encode(value) for value in index],
            }
        if isinstance(index, pd.RangeIndex):
            return {
                "kind": "range",
                "name": cls._encode(index.name),
                "start": index.start,
                "stop": index.stop,
                "step": index.step,
            }
        return {
            "kind": "index",
            "name": cls._encode(index.name),
            "dtype": str(index.dtype),
            "values": [cls._encode(value) for value in index],
        }

    @classmethod
    def _encode(cls, value: Any) -> Any:
        if isinstance(value, pd.DataFrame):
            return {
                "__type__": "dataframe",
                "index": cls._encode_index(value.index),
                "columns": [cls._encode(column) for column in value.columns],
                "dtypes": [str(dtype) for dtype in value.dtypes],
                "values": [
                    [cls._encode(value.iat[row, col]) for col in range(value.shape[1])]
                    for row in range(value.shape[0])
                ],
            }
        if isinstance(value, pd.Series):
            return {
                "__type__": "series",
                "index": cls._encode_index(value.index),
                "name": cls._encode(value.name),
                "dtype": str(value.dtype),
                "values": [cls._encode(item) for item in value.array],
            }
        if isinstance(value, pd.Index):
            return {"__type__": "index", "value": cls._encode_index(value)}
        if isinstance(value, pd.Timestamp):
            return {"__type__": "timestamp", "value": value.isoformat()}
        if isinstance(value, datetime):
            return {"__type__": "datetime", "value": value.isoformat()}
        if isinstance(value, date):
            return {"__type__": "date", "value": value.isoformat()}
        if isinstance(value, np.ndarray):
            return {
                "__type__": "ndarray",
                "dtype": str(value.dtype),
                "shape": list(value.shape),
                "values": [cls._encode(item) for item in value.reshape(-1)],
            }
        if isinstance(value, np.floating):
            return {"__type__": "numpy-float", "dtype": str(value.dtype), "bits": cls._float_hex(float(value))}
        if isinstance(value, float):
            return {"__type__": "float64", "bits": cls._float_hex(value)}
        if isinstance(value, np.integer):
            return {"__type__": "int", "value": int(value)}
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, Enum):
            return cls._encode(value.value)
        if is_dataclass(value):
            return cls._encode(asdict(value))
        if isinstance(value, Mapping):
            if any(not isinstance(key, str) for key in value):
                raise ResearchArtifactError("Snapshot mapping keys must be strings.")
            return {key: cls._encode(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return {"__type__": "tuple", "values": [cls._encode(item) for item in value]}
        if isinstance(value, list):
            return [cls._encode(item) for item in value]
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if value is pd.NaT:
            return {"__type__": "nat"}
        raise ResearchArtifactError(f"Unsupported snapshot value: {type(value).__name__}.")

    @classmethod
    def _decode_index(cls, value: dict[str, Any]) -> pd.Index:
        name = cls._decode(value.get("name"))
        if value["kind"] == "range":
            return pd.RangeIndex(value["start"], value["stop"], value["step"], name=name)
        decoded = [cls._decode(item) for item in value["values"]]
        if value["kind"] == "datetime":
            index = pd.DatetimeIndex(decoded, name=name)
            timezone = value.get("timezone")
            if timezone:
                index = index.tz_convert(timezone) if index.tz is not None else index.tz_localize(timezone)
            return index
        index = pd.Index(decoded, name=name)
        try:
            return index.astype(value["dtype"])
        except (TypeError, ValueError):
            return index

    @classmethod
    def _decode(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [cls._decode(item) for item in value]
        if not isinstance(value, dict):
            return value
        kind = value.get("__type__")
        if kind is None:
            return {key: cls._decode(item) for key, item in value.items()}
        if kind == "float64":
            return struct.unpack(">d", bytes.fromhex(value["bits"]))[0]
        if kind == "numpy-float":
            raw = struct.unpack(">d", bytes.fromhex(value["bits"]))[0]
            return np.dtype(value["dtype"]).type(raw)
        if kind == "int":
            return int(value["value"])
        if kind == "timestamp":
            return pd.Timestamp(value["value"])
        if kind == "datetime":
            return datetime.fromisoformat(value["value"])
        if kind == "date":
            return date.fromisoformat(value["value"])
        if kind == "nat":
            return pd.NaT
        if kind == "tuple":
            return tuple(cls._decode(item) for item in value["values"])
        if kind == "index":
            return cls._decode_index(value["value"])
        if kind == "ndarray":
            decoded = [cls._decode(item) for item in value["values"]]
            return np.asarray(decoded, dtype=value["dtype"]).reshape(value["shape"])
        if kind == "series":
            series = pd.Series(
                [cls._decode(item) for item in value["values"]],
                index=cls._decode_index(value["index"]),
                name=cls._decode(value["name"]),
            )
            return series.astype(value["dtype"])
        if kind == "dataframe":
            rows = [
                [cls._decode(item) for item in row]
                for row in value["values"]
            ]
            frame = pd.DataFrame(
                rows,
                index=cls._decode_index(value["index"]),
                columns=[cls._decode(column) for column in value["columns"]],
            )
            for index, dtype in enumerate(value["dtypes"]):
                frame.iloc[:, index] = frame.iloc[:, index].astype(dtype)
            return frame
        raise ResearchArtifactError(f"Unsupported snapshot type marker: {kind!r}.")

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(
            value,
            sort_keys=False,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    @staticmethod
    def fingerprint(value: Any) -> str:
        encoded = ResearchDataStore._encode(value)
        return hashlib.sha256(ResearchDataStore._canonical_json(encoded)).hexdigest()

    @classmethod
    def runtime_provenance(cls) -> dict[str, Any]:
        lock_path = cls.ROOT / "requirements-paper.lock"
        if not lock_path.is_file():
            raise ResearchArtifactError("requirements-paper.lock is missing.")
        lock_bytes = lock_path.read_bytes()
        locked: dict[str, str] = {}
        for line in lock_bytes.decode("utf-8").splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+)==([^;\s]+)$", line.strip())
            if match:
                normalized = re.sub(r"[-_.]+", "-", match.group(1)).lower()
                locked[normalized] = match.group(2)
        installed = {
            re.sub(r"[-_.]+", "-", distribution.metadata["Name"]).lower(): distribution.version
            for distribution in importlib.metadata.distributions()
            if distribution.metadata.get("Name")
        }
        environment = {
            name: installed.get(name)
            for name in sorted(locked)
        }
        mismatches = {
            name: {"locked": expected, "installed": environment[name]}
            for name, expected in sorted(locked.items())
            if environment[name] != expected
        }
        source_hash = hashlib.sha256()
        for path in sorted(cls.ROOT.glob("*.py"), key=lambda item: item.name):
            if path.name.startswith("test_") or path.name.endswith("_test.py"):
                continue
            source_hash.update(path.name.encode("utf-8"))
            source_hash.update(b"\0")
            source_hash.update(path.read_bytes())
            source_hash.update(b"\0")
        revision = "unknown"
        try:
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cls.ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        revision = __import__("os").environ.get("PAPER_CODE_REVISION", revision)
        packages_fingerprint = hashlib.sha256(
            cls._canonical_json(environment)
        ).hexdigest()
        return {
            "code_revision": revision,
            "source_tree_sha256": source_hash.hexdigest(),
            "dependency_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
            "dependency_environment_sha256": packages_fingerprint,
            "dependency_mismatches": mismatches,
            "python_version": sys.version,
            "locked_packages": environment,
        }

    def write_snapshot(
        self,
        inputs: dict[str, Any],
        *,
        input_fingerprint: str,
        configuration: dict[str, Any],
        provenance: dict[str, Any],
        execution_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        configuration_fingerprint = self.fingerprint(configuration)
        execution_state_fingerprint = self.fingerprint(execution_state)
        envelope = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "input_fingerprint": input_fingerprint,
            "configuration_fingerprint": configuration_fingerprint,
            "execution_state_fingerprint": execution_state_fingerprint,
            "provenance": provenance,
            "configuration": configuration,
            "execution_state": execution_state,
            "inputs": inputs,
        }
        encoded = self._canonical_json(self._encode(envelope))
        compressed = gzip.compress(encoded, mtime=0)
        artifact_id = hashlib.sha256(compressed).hexdigest()
        destination = self.directory / artifact_id[:2] / f"{artifact_id[2:]}.json.gz"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != artifact_id:
                raise ResearchArtifactError("Existing content-addressed artifact is corrupt.")
        else:
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                    temporary.write(compressed)
                    temporary.flush()
                    import os
                    os.fsync(temporary.fileno())
                temporary_path.replace(destination)
            except OSError as exc:
                raise ResearchArtifactError(f"Unable to persist research snapshot: {exc}") from exc
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
        return {
            "artifact_id": artifact_id,
            "relative_path": str(destination.relative_to(self.directory)),
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "input_fingerprint": input_fingerprint,
            "configuration_fingerprint": configuration_fingerprint,
            "execution_state_fingerprint": execution_state_fingerprint,
            "provenance": provenance,
        }

    def load_snapshot(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get("format") != self.FORMAT:
            raise ResearchArtifactError("Unsupported research snapshot format.")
        if manifest.get("schema_version") != self.SCHEMA_VERSION:
            raise ResearchArtifactError("Unsupported research snapshot schema.")
        artifact_id = manifest.get("artifact_id")
        if not isinstance(artifact_id, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_id):
            raise ResearchArtifactError("Invalid research artifact identifier.")
        expected_relative = Path(artifact_id[:2]) / f"{artifact_id[2:]}.json.gz"
        if manifest.get("relative_path") != str(expected_relative):
            raise ResearchArtifactError("Research artifact path does not match its content hash.")
        path = self.directory / expected_relative
        try:
            compressed = path.read_bytes()
            if hashlib.sha256(compressed).hexdigest() != artifact_id:
                raise ResearchArtifactError("Research snapshot content hash mismatch.")
            envelope = self._decode(json.loads(gzip.decompress(compressed)))
        except (OSError, gzip.BadGzipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ResearchArtifactError(f"Unable to load research snapshot: {exc}") from exc
        if envelope.get("format") != self.FORMAT or envelope.get("schema_version") != self.SCHEMA_VERSION:
            raise ResearchArtifactError("Research snapshot envelope version mismatch.")
        if envelope.get("input_fingerprint") != manifest.get("input_fingerprint"):
            raise ResearchArtifactError("Research snapshot input fingerprint mismatch.")
        if envelope.get("configuration_fingerprint") != manifest.get("configuration_fingerprint"):
            raise ResearchArtifactError("Research snapshot configuration fingerprint mismatch.")
        if self.fingerprint(envelope["configuration"]) != manifest.get("configuration_fingerprint"):
            raise ResearchArtifactError("Research snapshot configuration has changed.")
        if envelope.get("execution_state_fingerprint") != manifest.get(
            "execution_state_fingerprint"
        ):
            raise ResearchArtifactError("Research snapshot execution state fingerprint mismatch.")
        if self.fingerprint(envelope.get("execution_state")) != manifest.get(
            "execution_state_fingerprint"
        ):
            raise ResearchArtifactError("Research snapshot execution state has changed.")
        return envelope
