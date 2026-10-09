"""
Interactive matching demo for a single row (e.g., jqc).

What: Runs the matching filters step-by-step (ICSD → formula+SG → CIF → fallback)
and prints candidates after each stage, so you can see how loosening filters
affects results.

Usage examples:
  python Tests/play_matching.py --csv train.csv --split train --id jqc
  python Tests/play_matching.py --csv test.csv --split test --id abc --no-cif

Requirements:
  - pandas, pymatgen, mp-api
  - Set MP API key in environment or pass --api-key
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict

import pandas as pd

# Ensure project root is on sys.path so `src` can be imported when running this file directly
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.materials_api import MaterialsProjectAPI
from src.matching import (
    MatchCandidate,
    filter_icsd,
    filter_formula_only,
    filter_formula_sg,
    filter_cif_match,
    normalize_formula,
    normalize_spacegroup_symbol,
    resolve_cif_path,
    CIF_MATCH_TIERS,
)


def _coerce_int_or_none(value: Any):
    try:
        if value is None:
            return None
        s = str(value).strip()
        if s == "" or s.lower() == "nan":
            return None
        return int(float(s)) if "." in s else int(s)
    except Exception:
        return None


def print_candidates(title: str, items: list[MatchCandidate]):
    print(f"\n== {title} ==")
    if not items:
        print("(no candidates)")
        return
    for i, c in enumerate(items, 1):
        print(f"{i:2d}. {c.mpid:>12}  {c.reason:12}  score={c.score}  notes={json.dumps(c.notes, default=str)}")


def merge_and_rank(
    cand_lists: list[list[MatchCandidate]],
    *,
    tried_cif_tiers: list[str] | None = None,
):
    """
    Merge candidates across stages by MPID, keep best score, and collate reasons/notes.
    Returns a list of dicts sorted by score desc, non-deprecated first.
    """
    agg: dict[str, dict] = {}
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
            # pick symmetry fields if present
            for k in ("spg_number", "spg_symbol", "crystal_system"):
                v = c.notes.get(k)
                if v is not None and d.get(k) is None:
                    d[k] = v
            # sg relation (from formula-only)
            rel = c.notes.get("sg_relation")
            if rel is not None:
                # prefer exact > same_system > mismatch
                rank = {"exact": 3, "same_system": 2, "mismatch": 1}.get(str(rel), 0)
                cur = {"exact": 3, "same_system": 2, "mismatch": 1}.get(str(d.get("sg_relation")), 0)
                if rank > cur:
                    d["sg_relation"] = rel
            # cif tier
            if c.reason == "cif_match":
                d["cif_tier"] = c.notes.get("tier") or "strict"

    rows = list(agg.values())
    # mark no-cif-match when tiers were tried
    if tried_cif_tiers:
        for r in rows:
            if r.get("cif_tier") is None:
                r["cif_tier"] = f"no (up to {tried_cif_tiers[-1]})"

    # sort: non-deprecated first, then score desc, then mpid
    rows.sort(key=lambda r: (r.get("deprecated") is True, -int(r["score"]), r["mpid"]))
    return rows


def print_aggregate(rows: list[dict]):
    print("\n== Aggregate candidates ==")
    if not rows:
        print("(no candidates)")
        return
    # Columns: rank, mpid, score, reasons, sg_relation, sg, crystal, cif
    def to_s(v):
        return "" if v is None else str(v)
    header = (
        f"{'#':>2}  {'mpid':>12}  {'score':>5}  {'reasons':<24}  {'sg_rel':<12}  {'SG':<8}  {'crystal':<10}  {'CIF':<18}  {'deprecated':<10}"
    )
    print(header)
    print("-" * len(header))
    for i, r in enumerate(rows, 1):
        sg = r.get("spg_symbol") or r.get("spg_number") or ""
        reasons = ",".join(sorted(r.get("reasons", [])))[:24]
        print(
            f"{i:2d}  {r['mpid']:>12}  {int(r['score']):>5}  {reasons:<24}  {to_s(r.get('sg_relation')):<12}  {to_s(sg):<8}  {to_s(r.get('crystal_system')):<10}  {to_s(r.get('cif_tier')):<18}  {str(r.get('deprecated')):<10}"
        )


def main():
    p = argparse.ArgumentParser(description="Step-by-step Materials Project matching demo")
    p.add_argument("--csv", type=Path, required=True, help="Path to the dataset CSV (merged or original)")
    p.add_argument("--split", default=None, help="Dataset split label (optional; not needed if using unified cifs/ and/or a cif_path column)")
    p.add_argument("--id", dest="row_id", required=True, help="Row ID (e.g., jqc)")
    p.add_argument("--row-id-field", default="id", help="CSV column for the row id (default: id)")
    p.add_argument("--api-key", default=None, help="MP API key (optional; else use environment)")
    p.add_argument("--no-icsd", action="store_true", help="Skip ICSD stage")
    p.add_argument("--no-formula-sg", action="store_true", help="Skip formula+SG stage")
    p.add_argument("--no-cif", action="store_true", help="Skip CIF matching stage")
    p.add_argument("--no-fallback", action="store_true", help="Skip formula-only fallback stage")
    p.add_argument("--no-deprecated", action="store_true", help="Do not include deprecated docs in fallbacks")
    p.add_argument("--show-all", action="store_true", help="Show all stages without exiting early on first success")
    p.add_argument("--debug", action="store_true", help="Print API key detection and quick query diagnostics")
    # CIF matching control: keep legacy --matcher-loose, add tier and sweep
    p.add_argument("--matcher-loose", action="store_true", help="Alias for --matcher-tier loose")
    p.add_argument("--matcher-tier", choices=["strict", "medium", "loose", "very_loose"], help="Choose CIF matcher tier")
    p.add_argument("--matcher-sweep", action="store_true", help="Try tiers in order until a match occurs")
    p.add_argument("--use-structure-sg", action="store_true", help="Infer SG from MP structures for better SG matching/scoring")
    args = p.parse_args()

    # Load CSV
    df = pd.read_csv(args.csv)

    # Auto-detect the ID column if the provided one doesn't exist
    target_id = str(args.row_id)
    row_id_field = args.row_id_field
    used_field = None

    def _try_match(col_name: str):
        try:
            col = df[col_name].astype(str)
        except Exception:
            return None
        hits = df[col == target_id]
        return hits if not hits.empty else None

    matches = None
    if row_id_field in df.columns:
        matches = _try_match(row_id_field)
        if matches is not None:
            used_field = row_id_field
    if matches is None:
        candidates = [
            "id",
            "ID",
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
            "name",
            "Name",
        ]
        for c in candidates:
            if c in df.columns:
                matches = _try_match(c)
                if matches is not None:
                    used_field = c
                    break
    if matches is None:
        # As a last attempt, scan all columns for an exact string hit
        for c in df.columns:
            try:
                col = df[c].astype(str)
            except Exception:
                continue
            hits = df[col == target_id]
            if not hits.empty:
                used_field = c
                matches = hits
                break
    if matches is None:
        cols = ", ".join(map(str, df.columns))
        raise SystemExit(
            f"Could not find a row with value {target_id!r} in any column.\n"
            f"Available columns: {cols}\n"
            f"If you know the column name, pass --row-id-field <name>."
        )
    row = matches.iloc[0]
    print(f"Using ID column: {used_field}")

    # Normalize fields
    formula = normalize_formula(row.get("Reduced Composition", ""))
    spg_no = _coerce_int_or_none(row.get("Space group #"))
    spg_sym = normalize_spacegroup_symbol(row.get("Space group"))
    icsd_id = _coerce_int_or_none(row.get("ICSD ID"))
    print(f"Row: id={row[used_field]!r}, formula={formula}, sg#={spg_no}, sg={spg_sym}")

    # API
    api_key = args.api_key or os.environ.get("MP_API_KEY") or os.environ.get("MAPI_KEY")
    api = MaterialsProjectAPI(api_key=api_key)

    # Optional debug
    if args.debug:
        print(f"DEBUG: has_api_key={bool(api_key)}")
        try:
            _summ = api.by_formula(formula, include_deprecated=not args.no_deprecated)
            print(f"DEBUG: by_formula count={len(_summ)}")
        except Exception as e:
            print(f"DEBUG: query error: {e}")

    # 1) ICSD stage
    if not args.no_icsd and icsd_id is not None:
        cand_icsd = filter_icsd(icsd_id=icsd_id, api=api, include_deprecated_initial=False, include_deprecated_retry=True)
        print_candidates("ICSD", cand_icsd)
        if cand_icsd and not args.show_all:
            return
    else:
        print("\n== ICSD ==\n(skipped or no ICSD ID)")

    # 2) Formula + Space Group
    if not args.no_formula_sg and (spg_no is not None or spg_sym is not None):
        cand_sg = filter_formula_sg(
            formula=formula,
            spg_number=spg_no,
            spg_symbol=spg_sym,
            api=api,
            include_deprecated=not args.no_deprecated,
            allow_same_system=True,
            use_structure_sg=args.use_structure_sg,
        )
        print_candidates("Formula + SG", cand_sg)
        if cand_sg and not args.show_all:
            return
    else:
        print("\n== Formula + SG ==\n(skipped or no SG info)")

    # 3) CIF matching
    if not args.no_cif:
        # Prefer explicit cif_path column if present
        cif_path_val = row.get("cif_path")
        if isinstance(cif_path_val, str) and cif_path_val.strip():
            cp = Path(cif_path_val)
            cif_path = cp if cp.is_absolute() else (args.csv.parent / cp)
        else:
            # Use the detected/selected field for CIF mapping
            cif_path = resolve_cif_path(str(row[used_field]), split=args.split, base_dir=args.csv.parent)
        # Determine tier/sweep options
        tier_choice = args.matcher_tier or ("loose" if args.matcher_loose else None)
        cand_cif = filter_cif_match(
            formula=formula,
            cif_path=cif_path,
            api=api,
            include_deprecated_candidates=not args.no_deprecated,
            matcher_loose=args.matcher_loose,
            tier=tier_choice,
            sweep=args.matcher_sweep,
        )
        print(f"CIF path: {cif_path} -> {'exists' if cif_path.exists() else 'missing'}")
        print_candidates("CIF match", cand_cif)
        if cand_cif and not args.show_all:
            return
    else:
        print("\n== CIF match ==\n(skipped)")

    # 4) Formula-only fallback
    if not args.no_fallback:
        cand_fallback = filter_formula_only(
            formula=formula,
            api=api,
            include_deprecated=not args.no_deprecated,
            spg_number=spg_no,
            spg_symbol=spg_sym,
            use_structure_sg=args.use_structure_sg,
        )
        print_candidates("Formula-only fallback", cand_fallback)
    else:
        print("\n== Formula-only fallback ==\n(skipped)")

    # 5) Aggregate view across stages
    tried_tiers = None
    if not args.no_cif:
        if args.matcher_sweep:
            tried_tiers = list(CIF_MATCH_TIERS)
        elif args.matcher_tier:
            tried_tiers = [args.matcher_tier]
        elif args.matcher_loose:
            tried_tiers = ["loose"]
        else:
            tried_tiers = ["strict"]

    agg_rows = merge_and_rank([
        locals().get('cand_icsd', []) or [],
        locals().get('cand_sg', []) or [],
        locals().get('cand_cif', []) or [],
        locals().get('cand_fallback', []) or [],
    ], tried_cif_tiers=tried_tiers)
    print_aggregate(agg_rows)


if __name__ == "__main__":
    main()
