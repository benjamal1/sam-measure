"""Non-interactive end-to-end pipeline orchestrator — the walking-skeleton proof.

Drives segment -> export -> measure -> calibrate -> build_csv for one thread photo,
with the segmentation click supplied programmatically (standing in for the GUI click a
human drives interactively via segment.click_loop / segment.segment_export). Real
multi-thread runs use the same stage scripts per D-06; this orchestrator proves the
shape end-to-end on one thread.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np
import pandas as pd
from PIL import Image

from calibrate.ruler_scale import px_per_cm, write_calibration_csv
from join.build_final_csv import build_final_csv
from measure.measure_masks import measure_folder
from pipeline.manifest import add_calibration, add_input, add_output, new_manifest, write_manifest
from segment.export import export_mask
from segment.naming import PhotoMetadata, canonical_stem
from segment.sam2_session import load_predictor
from segment.sam2_session import predict_mask as _predict_mask


def run(
    photo_path: Path,
    click_points: list[tuple[float, float]],
    click_labels: list[int],
    ruler_path: Path,
    ruler_points: list[tuple[float, float]],
    known_cm_span: float,
    date: str,
    batch: str,
    condition: str,
    thread: str,
    data_root: Path,
    *,
    force: bool = False,
) -> pd.DataFrame:
    from datetime import datetime, timezone

    data_root = Path(data_root)
    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"
    csv_dir = data_root / "csv"
    calibration_dir = data_root / "calibration"

    year, month, day = (int(p) for p in date.split("-"))
    from datetime import date as date_cls
    meta = PhotoMetadata(
        batch=batch, batch_start_date=None, condition=condition, day="",
        date=date_cls(year, month, day), thread=thread, source_path=photo_path,
    )
    stem = canonical_stem(meta, thread)
    mask_path = masks_dir / f"{stem}.png"
    qc_path = qc_dir / f"{stem}_overlay.png"

    manifest = new_manifest("run_pipeline", datetime.now(timezone.utc).isoformat())
    manifest = add_input(manifest, str(photo_path))

    if mask_path.exists() and not force:
        manifest = add_output(manifest, stem=stem, action="skipped", mask_path=mask_path, qc_path=qc_path)
    else:
        predictor = load_predictor()
        image_rgb = np.array(Image.open(photo_path).convert("RGB"))
        mask = _predict_mask(predictor, image_rgb, click_points, click_labels)
        export_mask(mask, image_rgb, stem, masks_dir=masks_dir, qc_dir=qc_dir)
        manifest = add_output(manifest, stem=stem, action="written", mask_path=mask_path, qc_path=qc_path)

    measure_folder(masks_dir, csv_dir / "measurements.csv")

    factor = px_per_cm(ruler_points[0], ruler_points[1], known_cm_span)
    write_calibration_csv(
        [{"date": date, "batch": batch, "px_per_cm": factor, "ruler_source_path": str(ruler_path)}],
        calibration_dir / "calibration.csv",
    )
    manifest = add_calibration(manifest, thread=thread, date=date, batch=batch, px_per_cm=factor, ruler_source_path=str(ruler_path))

    result = build_final_csv(
        csv_dir / "measurements.csv", calibration_dir / "calibration.csv", csv_dir / "final.csv"
    )

    write_manifest(manifest, data_root)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the end-to-end walking-skeleton pipeline for one thread")
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--click-x", type=float, required=True)
    parser.add_argument("--click-y", type=float, required=True)
    parser.add_argument("--ruler", type=Path, required=True)
    parser.add_argument("--ruler-p1", type=float, nargs=2, required=True)
    parser.add_argument("--ruler-p2", type=float, nargs=2, required=True)
    parser.add_argument("--span", type=float, default=0.5)
    parser.add_argument("--date", type=str, required=True)
    parser.add_argument("--batch", type=str, default="")
    parser.add_argument("--condition", type=str, default="")
    parser.add_argument("--thread", type=str, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--force", action="store_true", default=False)
    args = parser.parse_args()

    df = run(
        photo_path=args.photo,
        click_points=[(args.click_x, args.click_y)],
        click_labels=[1],
        ruler_path=args.ruler,
        ruler_points=[tuple(args.ruler_p1), tuple(args.ruler_p2)],
        known_cm_span=args.span,
        date=args.date,
        batch=args.batch,
        condition=args.condition,
        thread=args.thread,
        data_root=args.data_root,
        force=args.force,
    )
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
