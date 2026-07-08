"""Pure per-run audit manifest builders (CSV-05, D2-05).

Immutable: every add_* function returns a NEW manifest dict, never mutates its argument.
No torch/cv2/sam2 import — pure stdlib json/pathlib/datetime.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def new_manifest(run_kind: str, started_at: str) -> dict:
    return {
        "run_kind": run_kind,
        "started_at": started_at,
        "inputs": [],
        "outputs": [],
        "calibration": [],
        "errors": [],
    }


def add_input(manifest: dict, source_path: str) -> dict:
    new = dict(manifest)
    new["inputs"] = manifest["inputs"] + [{"source_path": str(source_path)}]
    return new


def add_output(manifest: dict, stem: str, action: str, mask_path: str, qc_path: str) -> dict:
    new = dict(manifest)
    new["outputs"] = manifest["outputs"] + [{
        "stem": stem, "action": action, "mask_path": str(mask_path), "qc_path": str(qc_path),
    }]
    return new


def add_calibration(manifest: dict, thread: str, date: str, batch: str, px_per_cm: float, ruler_source_path: str) -> dict:
    new = dict(manifest)
    new["calibration"] = manifest["calibration"] + [{
        "thread": thread, "date": date, "batch": batch,
        "px_per_cm": px_per_cm, "ruler_source_path": str(ruler_source_path),
    }]
    return new


def add_error(manifest: dict, stage: str, message: str, source_path: str) -> dict:
    new = dict(manifest)
    new["errors"] = manifest["errors"] + [{"stage": stage, "message": message, "source_path": str(source_path)}]
    return new


def write_manifest(manifest: dict, data_root: Path, now: datetime | None = None) -> Path:
    data_root = Path(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    path = data_root / f"manifest_{ts}.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path
