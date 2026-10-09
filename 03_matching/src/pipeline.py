from __future__ import annotations

"""
CSV-facing utilities to run the matching pipeline over train/test files.

What: Convenience functions to apply `match_row` row-by-row and return a
DataFrame with `best_mpid` and `candidates` columns.

Why: Keep notebook/scripts clean and let the core logic live in `matching`.
"""

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    pd = None  # type: ignore

from .materials_api import MaterialsProjectAPI
from .matching import MatchResult, match_row


def run_dataframe(
    df,  # pandas.DataFrame
    split: str,
    api: MaterialsProjectAPI,
    *,
    row_id_field: str = "id",
    include_deprecated_fallback: bool = True,
    cif_dir_map: Optional[Mapping[str, Path]] = None,
    base_dir: Optional[Path] = None,
):
    """
    Apply the matching pipeline over a pandas DataFrame.

    What: Adds `best_mpid` and `candidates` columns.
    Why: Simple integration point for notebooks and scripts.
    """
    if pd is None:  # pragma: no cover
        raise ImportError("pandas is required to run the CSV pipeline")

    def _apply_row(row: Any) -> MatchResult:
        return match_row(
            row=row,
            split=split,
            api=api,
            row_id_field=row_id_field,
            include_deprecated_fallback=include_deprecated_fallback,
            cif_dir_map=cif_dir_map,
            base_dir=base_dir,
        )

    results = df.apply(_apply_row, axis=1)
    df = df.copy()
    df["best_mpid"] = results.map(lambda r: r.best_mpid)
    df["candidates"] = results.map(
        lambda r: [
            {"mpid": c.mpid, "reason": c.reason, "score": c.score, "notes": c.notes}
            for c in r.candidates
        ]
    )
    return df


def run_csv(
    csv_path: Path,
    split: str,
    api: MaterialsProjectAPI,
    *,
    row_id_field: str = "id",
    include_deprecated_fallback: bool = True,
    cif_dir_map: Optional[Mapping[str, Path]] = None,
):
    """
    Load a CSV and apply the matching pipeline, returning a DataFrame.

    What: Thin wrapper around `run_dataframe` for convenience.
    Why: Allows quick usage without manual DataFrame setup boilerplate.
    """
    if pd is None:  # pragma: no cover
        raise ImportError("pandas is required to run the CSV pipeline")

    df = pd.read_csv(csv_path)
    return run_dataframe(
        df=df,
        split=split,
        api=api,
        row_id_field=row_id_field,
        include_deprecated_fallback=include_deprecated_fallback,
        cif_dir_map=cif_dir_map,
        base_dir=csv_path.parent,
    )

