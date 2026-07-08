"""Walking-skeleton proof: real photo + programmatic click -> correct final.csv row.

Marked slow+integration. Skips cleanly if real Nextcloud data is unavailable.
"""
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from run_pipeline import run

EXACT_HEADER = (
    "Thread,Batch,Condition,Date,Conversion (pixels/cm),"
    "Avg diameter(px),StDev(px),AvgDiameter(mm),StDev(mm)"
)


@pytest.mark.slow
@pytest.mark.integration
def test_walking_skeleton_end_to_end(sample_photo_path, ruler_photo_path, data_root, ground_truth_imagej):
    df = run(
        photo_path=sample_photo_path,
        click_points=[(2740, 1534)],
        click_labels=[1],
        ruler_path=ruler_photo_path,
        ruler_points=[(0.0, 0.0), (400.0, 0.0)],
        known_cm_span=0.5,
        date="2025-08-03",
        batch="",
        condition="",
        thread="5.11",
        data_root=data_root,
    )

    final_csv = data_root / "csv" / "final.csv"
    assert final_csv.exists()

    header_line = final_csv.read_text().splitlines()[0]
    assert header_line == EXACT_HEADER

    assert len(df) == 1
    row = df.iloc[0]
    assert row["Thread"] == "5.11"

    avg_mm = row["AvgDiameter(mm)"]
    assert avg_mm > 0
    assert 0.3 <= avg_mm <= 3.0, (
        f"AvgDiameter(mm)={avg_mm} outside loose plausibility band "
        f"(ImageJ ground truth for 5.11 is {ground_truth_imagej['5.11']['avg_diameter_mm']})"
    )
