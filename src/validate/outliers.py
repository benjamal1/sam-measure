"""Pure IQR-based outlier flagging within (date,batch,condition) groups.

QOL-02 (pulled forward from v2 deferral, per user request this plan): a thread whose
area_px or avg_diameter_px is a statistical outlier within its own sibling group gets a
flag column, so the user can jump to its QC overlay for a mislabel check. Advisory only —
never blocks/hard-fails a run (see this plan's threat_model).

Pure module — no I/O, no SAM2/torch/cv2 import (mirrors src/validate/imagej_validation.py's
purity convention).
"""
from __future__ import annotations

import pandas as pd


def _append_reason(existing: str, reason: str) -> str:
    return f"{existing}; {reason}" if existing else reason


def flag_outliers(
    rows: list[dict],
    group_keys: tuple[str, ...] = ("date", "batch", "condition"),
    value_keys: tuple[str, ...] = ("area_px", "avg_diameter_px"),
) -> list[dict]:
    """Flag rows whose value_keys are IQR outliers within their own (date,batch,condition)
    sibling group (standard rule: below Q1-1.5*IQR or above Q3+1.5*IQR), independently per
    value_key. A row is flagged if ANY value_key is an outlier in its group.

    Groups with fewer than 4 rows are never flagged (avoids false positives on tiny
    groups) — flag defaults to False for those. Returns a NEW list of dicts; never mutates
    the input rows.
    """
    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["flag"] = False
    df["flag_reason"] = ""

    for group_key, group_df in df.groupby(list(group_keys), sort=False):
        if len(group_df) < 4:
            continue

        group_label = group_key if isinstance(group_key, tuple) else (group_key,)
        group_desc = "/".join(str(v) for v in group_label)

        for value_key in value_keys:
            values = pd.to_numeric(group_df[value_key])
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr

            outlier_idx = group_df.index[(values < lower) | (values > upper)]
            if len(outlier_idx) == 0:
                continue

            reason = f"{value_key} outlier in {group_desc}"
            df.loc[outlier_idx, "flag"] = True
            for idx in outlier_idx:
                df.at[idx, "flag_reason"] = _append_reason(df.at[idx, "flag_reason"], reason)

    return df.to_dict(orient="records")
