from __future__ import annotations

"""
Batch matcher for the unified Obelix dataset.

What: Reads a CSV (merged or original), applies the matching pipeline for each row,
produces best_mpid and an aggregated candidate summary, and writes a results CSV.

Why: Run the exact same, tested filters at scale without touching core code.

Usage examples:
  # Sweep CIF tiers, use structure-derived SG, include deprecated docs
  python tools/batch_match.py --csv data/ObelixData.csv --out data/ObelixMatches.csv \
    --matcher-sweep --use-structure-sg

  # Restrict to a subset of IDs (one per line)
  python tools/batch_match.py --csv data/ObelixData.csv --out data/subset_matches.csv \
    --ids-file ids.txt --matcher-sweep --use-structure-sg

  # Choose any output path with --out; filenames above are examples.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Ensure project root is on sys.path so `src` can be imported when running this file directly
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.materials_api import MaterialsProjectAPI
from src.matching import (
    filter_icsd,
    filter_formula_sg,
    filter_cif_match,
    filter_formula_only,
    is_stoichiometric_label,
    normalize_formula,
    resolve_cif_path,
    CIF_MATCH_TIERS,
)


ID_CANDIDATES = [
    "ID",
    "id",
    "Id",
    "row_id",
    "Row ID",
    "RowID",
    "material_id",
    "materialId",
    "structure_id",
    "structureId",
    "uid",
    "UID",
    "entry_id",
    "Entry ID",
]


def _dedupe_preserve(seq: List[Any], *, key=None) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for item in seq:
        marker = key(item) if key else item
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def find_id_column(df: pd.DataFrame, preferred: Optional[str] = None) -> str:
    if preferred and preferred in df.columns:
        return preferred
    for c in ID_CANDIDATES:
        if c in df.columns:
            return c
    # fallback: first column
    return str(df.columns[0])


def coerce_int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            # Avoid surprising behavior if a list slips through
            return coerce_int_or_none(next(iter(value), None))
        s = str(value).strip()
        if s == "" or s.lower() == "nan":
            return None
        return int(float(s)) if "." in s else int(s)
    except Exception:
        return None


def _normalize_cell(value: Any) -> Optional[Any]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            s = value.strip()
            if not s or s.lower() == "nan":
                return None
            return s
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _safe_get(row: pd.Series, column: Optional[str]) -> Optional[Any]:
    if not column:
        return None
    if column not in row.index:
        return None
    return _normalize_cell(row[column])


def _split_multi_field(value: Any, delimiter: str) -> List[str]:
    val = _normalize_cell(value)
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        items: List[str] = []
        for v in val:
            items.extend(_split_multi_field(v, delimiter))
        return items
    text = str(val)
    if delimiter:
        parts = text.split(delimiter)
    else:
        parts = [text]
    return [p.strip() for p in parts if p and p.strip()]


def _parse_sg_numbers(value: Any, delimiter: str) -> List[int]:
    numbers: List[int] = []
    for token in _split_multi_field(value, delimiter):
        maybe = coerce_int_or_none(token)
        if maybe is not None:
            numbers.append(maybe)
    return _dedupe_preserve(numbers)


def _parse_sg_symbols(value: Any, delimiter: str) -> List[str]:
    symbols: List[str] = []
    for token in _split_multi_field(value, delimiter):
        if token:
            symbols.append(token)
    return _dedupe_preserve(symbols, key=lambda s: s.lower())


def _parse_combined_sg(value: Any, delimiter: str) -> Tuple[List[int], List[str]]:
    numbers: List[int] = []
    symbols: List[str] = []
    for token in _split_multi_field(value, delimiter):
        if not token:
            continue
        sym = token
        num = None
        # Look for "(123)" pattern
        match = re.search(r"\(([^)]+)\)", token)
        if match:
            num = coerce_int_or_none(match.group(1))
            sym = token[: match.start()].strip()
        else:
            # If token is purely numeric, treat as number
            maybe = coerce_int_or_none(token)
            if maybe is not None:
                num = maybe
                sym = None
        if num is not None:
            numbers.append(num)
        if sym:
            symbols.append(sym.strip())
    return _dedupe_preserve(numbers), _dedupe_preserve(symbols, key=lambda s: s.lower())


def merge_and_rank(cand_lists: List[List[Dict]], tried_cif_tiers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Merge candidates across stages by MPID, keep best score, collate reasons/notes."""
    agg: Dict[str, Dict[str, Any]] = {}
    for lst in cand_lists:
        for c in lst:
            d = agg.setdefault(c.mpid, {
                "mpid": c.mpid,
                "score": -10**9,
                "reasons": set(),
                "deprecated": None,
                "sg_relation": None,
                "spg_number": None,
                "spg_symbol": None,
                "crystal_system": None,
                "cif_tier": None,
            })
            d["score"] = max(d["score"], c.score)
            d["reasons"].add(c.reason)
            dep = c.notes.get("deprecated")
            if dep is not None:
                d["deprecated"] = bool(dep)
            for k in ("spg_number", "spg_symbol", "crystal_system"):
                v = c.notes.get(k)
                if v is not None and d.get(k) is None:
                    d[k] = v
            rel = c.notes.get("sg_relation")
            if rel is not None:
                rank = {"exact": 3, "same_system": 2, "mismatch": 1}.get(str(rel), 0)
                cur = {"exact": 3, "same_system": 2, "mismatch": 1}.get(str(d.get("sg_relation")), 0)
                if rank > cur:
                    d["sg_relation"] = rel
            if c.reason == "cif_match":
                d["cif_tier"] = c.notes.get("tier") or "strict"

    rows = list(agg.values())
    if tried_cif_tiers:
        for r in rows:
            if r.get("cif_tier") is None:
                r["cif_tier"] = f"no (up to {tried_cif_tiers[-1]})"
    rows.sort(key=lambda r: (r.get("deprecated") is True, -int(r["score"]), r["mpid"]))
    # Convert reasons set to sorted string for outputs
    for r in rows:
        r["reasons"] = ",".join(sorted(r["reasons"]))
    return rows


def process_row(
    row: pd.Series,
    df_path: Path,
    api: MaterialsProjectAPI,
    *,
    row_id_field: str,
    formula_column: str,
    sg_symbol_column: Optional[str],
    sg_number_column: Optional[str],
    sg_combined_column: Optional[str],
    sg_delimiter: str,
    include_deprecated: bool,
    use_structure_sg: bool,
    matcher_tier: Optional[str],
    matcher_sweep: bool,
) -> Dict[str, Any]:
    # Normalize CSV fields
    rid = str(row[row_id_field])
    icsd_id = coerce_int_or_none(row.get("ICSD ID"))
    formula_source = _safe_get(row, formula_column) or row.get("Reduced Composition", "")
    if not is_stoichiometric_label(formula_source or ""):
        # Label is an acronym / oxidation-state notation / non-element string: it carries no
        # composition information, so no Materials Project link is attempted
        # (see matching.is_stoichiometric_label).
        return {"ID": rid, "best_mpid": None, "best_score": None,
                "best_reasons": "label_not_stoichiometric", "best_sg_relation": None,
                "best_spg_symbol": None, "best_spg_number": None, "best_crystal_system": None,
                "best_cif_tier": None, "best_deprecated": None, "candidates": []}
    formula = normalize_formula(formula_source or "")

    sg_numbers: List[int] = []
    sg_symbols: List[str] = []

    # Dedicated number/symbol columns
    if sg_number_column:
        sg_numbers.extend(_parse_sg_numbers(_safe_get(row, sg_number_column), sg_delimiter))
    if sg_symbol_column:
        sg_symbols.extend(_parse_sg_symbols(_safe_get(row, sg_symbol_column), sg_delimiter))

    # Combined column with entries like "Pm-3m (221); Pnma (62)"
    if sg_combined_column:
        combined_numbers, combined_symbols = _parse_combined_sg(_safe_get(row, sg_combined_column), sg_delimiter)
        sg_numbers.extend(combined_numbers)
        sg_symbols.extend(combined_symbols)

    # Final dedupe once all sources considered
    sg_numbers = _dedupe_preserve(sg_numbers)
    sg_symbols = _dedupe_preserve(sg_symbols, key=lambda s: s.lower())

    # Stage 1: ICSD
    cand_icsd = filter_icsd(icsd_id=icsd_id, api=api, include_deprecated_initial=False, include_deprecated_retry=True) if icsd_id is not None else []

    # Stage 2: Formula + SG
    cand_sg = []
    if sg_numbers or sg_symbols:
        cand_sg = filter_formula_sg(
            formula=formula,
            spg_number=sg_numbers,
            spg_symbol=sg_symbols,
            api=api,
            include_deprecated=include_deprecated,
            allow_same_system=True,
            use_structure_sg=use_structure_sg,
        )

    # Stage 3: CIF match
    # Prefer cif_path column if present
    cif_path_val = row.get("cif_path")
    if isinstance(cif_path_val, str) and cif_path_val.strip():
        cp = Path(cif_path_val)
        cif_path = cp if cp.is_absolute() else (df_path.parent / cp)
    else:
        cif_path = resolve_cif_path(rid, split=None, base_dir=df_path.parent)
    cand_cif = filter_cif_match(
        formula=formula,
        cif_path=cif_path,
        api=api,
        include_deprecated_candidates=include_deprecated,
        tier=matcher_tier,
        sweep=matcher_sweep,
    )

    # Stage 4: Formula-only
    cand_fallback = filter_formula_only(
        formula=formula,
        api=api,
        include_deprecated=include_deprecated,
        spg_number=sg_numbers,
        spg_symbol=sg_symbols,
        use_structure_sg=use_structure_sg,
    )

    # Aggregate and choose best
    tried_tiers = None
    if matcher_sweep:
        tried_tiers = list(CIF_MATCH_TIERS)
    elif matcher_tier:
        tried_tiers = [matcher_tier]
    rows = merge_and_rank([cand_icsd, cand_sg, cand_cif, cand_fallback], tried_cif_tiers=tried_tiers)

    best = rows[0] if rows else None
    return {
        "ID": rid,
        "best_mpid": best.get("mpid") if best else None,
        "best_score": int(best.get("score")) if best else None,
        "best_reasons": best.get("reasons") if best else None,
        "best_sg_relation": best.get("sg_relation") if best else None,
        "best_spg_symbol": best.get("spg_symbol") if best else None,
        "best_spg_number": best.get("spg_number") if best else None,
        "best_crystal_system": best.get("crystal_system") if best else None,
        "best_cif_tier": best.get("cif_tier") if best else None,
        "best_deprecated": best.get("deprecated") if best else None,
        "candidates": [
            {
                "mpid": r["mpid"],
                "score": int(r["score"]),
                "reasons": r["reasons"],
                "sg_relation": r.get("sg_relation"),
                "spg_symbol": r.get("spg_symbol"),
                "spg_number": r.get("spg_number"),
                "crystal_system": r.get("crystal_system"),
                "cif_tier": r.get("cif_tier"),
                "deprecated": r.get("deprecated"),
            }
            for r in rows
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="Batch match Materials Project candidates for a dataset")
    ap.add_argument("--csv", type=Path, required=True, help="Path to merged or original CSV")
    ap.add_argument("--out", type=Path, required=True, help="Path to write results CSV")
    ap.add_argument("--row-id-field", default=None, help="Explicit ID column name (optional)")
    ap.add_argument("--ids-file", type=Path, default=None, help="Optional file with one ID per line to process")
    ap.add_argument("--limit", type=int, default=None, help="Optional limit of rows to process")
    ap.add_argument("--formula-column", default="Reduced Composition", help="Column containing the formula/composition to normalize")
    ap.add_argument("--sg-symbol-column", default="Space group", help="Column containing space-group symbols (can be multi-valued)")
    ap.add_argument("--sg-number-column", default="Space group #", help="Column containing space-group numbers (can be multi-valued)")
    ap.add_argument(
        "--sg-combined-column",
        default=None,
        help="Column with combined entries like 'Pm-3m (221); Pnma (62)' (optional)",
    )
    ap.add_argument(
        "--sg-delimiter",
        default=";",
        help="Delimiter for multi-valued space-group columns (default ';')",
    )
    ap.add_argument(
        "--encoding",
        default=None,
        help="Encoding for CSV files (default utf-8 with latin-1 fallback)",
    )
    ap.add_argument("--api-key", default=None, help="MP API key (otherwise uses env)")
    ap.add_argument("--no-deprecated", action="store_true", help="Exclude deprecated docs from fallbacks")
    ap.add_argument("--use-structure-sg", action="store_true", help="Infer SG from MP structures for better SG matching/scoring")
    ap.add_argument("--matcher-loose", action="store_true", help="Alias for --matcher-tier loose")
    ap.add_argument("--matcher-tier", choices=["strict", "medium", "loose", "very_loose"], help="Choose CIF matcher tier")
    ap.add_argument("--matcher-sweep", action="store_true", help="Try CIF tiers in order until a match occurs")
    ap.add_argument("--debug", action="store_true", help="Print debug info per row")
    args = ap.parse_args()

    if args.csv.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(args.csv)
    else:
        if args.encoding:
            df = pd.read_csv(args.csv, encoding=args.encoding)
        else:
            try:
                df = pd.read_csv(args.csv)
            except UnicodeDecodeError:
                df = pd.read_csv(args.csv, encoding="latin1")
    id_col = find_id_column(df, args.row_id_field)

    def _normalize_column_arg(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    formula_column = args.formula_column or "Reduced Composition"
    sg_symbol_column = _normalize_column_arg(args.sg_symbol_column)
    sg_number_column = _normalize_column_arg(args.sg_number_column)
    sg_combined_column = _normalize_column_arg(args.sg_combined_column)
    sg_delimiter = args.sg_delimiter or ";"

    # Subset rows if requested
    ids_set = None
    if args.ids_file:
        with open(args.ids_file, "r", encoding="utf-8") as f:
            ids_set = {line.strip() for line in f if line.strip()}
        df = df[df[id_col].astype(str).isin(ids_set)]

    # Respect limit
    if args.limit is not None and args.limit >= 0:
        df = df.head(args.limit)

    api_key = args.api_key or os.environ.get("MP_API_KEY") or os.environ.get("MAPI_KEY")
    api = MaterialsProjectAPI(api_key=api_key)
    include_deprecated = not args.no_deprecated

    results: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        try:
            rec = process_row(
                row=row,
                df_path=args.csv,
                api=api,
                row_id_field=id_col,
                formula_column=formula_column,
                sg_symbol_column=sg_symbol_column,
                sg_number_column=sg_number_column,
                sg_combined_column=sg_combined_column,
                sg_delimiter=sg_delimiter,
                include_deprecated=include_deprecated,
                use_structure_sg=args.use_structure_sg,
                matcher_tier=(args.matcher_tier or ("loose" if args.matcher_loose else None)),
                matcher_sweep=args.matcher_sweep,
            )
            results.append(rec)
            if args.debug:
                print(f"Processed {rec['ID']}: best={rec['best_mpid']} score={rec['best_score']}")
        except Exception as e:
            if args.debug:
                print(f"Error processing row index {idx}: {e}")
            # Still append a stub record with error info
            rid = str(row.get(id_col))
            results.append({
                "ID": rid,
                "best_mpid": None,
                "best_score": None,
                "best_reasons": None,
                "best_sg_relation": None,
                "best_spg_symbol": None,
                "best_spg_number": None,
                "best_crystal_system": None,
                "best_cif_tier": None,
                "best_deprecated": None,
                "candidates": [],
                "error": str(e),
            })

    # Build output DataFrame
    out_df = pd.DataFrame(results)
    # Ensure candidates is JSON-serializable string
    out_df["candidates"] = out_df["candidates"].map(lambda x: json.dumps(x, default=str))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)
    print(f"Wrote results: {args.out} ({len(out_df)} rows)")


if __name__ == "__main__":
    main()

