#!/usr/bin/env python3
"""
build_master_dataset.py

Assembles the published SSE conductivity dataset in two forms from the pipeline outputs:
  - data/final/sse_conductivity_master.csv           : fully-provenanced master table
  - data/final/sse_conductivity_slim.csv: analysis/ML-ready slim table

The final tiered table (MyDatabase.csv) is the SPINE: the master has exactly the
same rows (none added/dropped); provenance (DOI, reported SG, ICSD, source) and
Materials Project match evidence (score, reasons, SG relation, candidates) are
attached by left-join.

Run:  python build_master_dataset.py            (uses its own folder as the root)
      python build_master_dataset.py <pkg_dir>  (explicit package root)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

PKG = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
FIN = PKG / "data" / "final"
INT = PKG / "data" / "interim"


def rd(path, **kw):
    """Read CSV as strings, tolerant of BOM and the non-UTF-8 bytes in the ACS export."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, keep_default_na=True, **kw)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, dtype=str, encoding="latin-1", keep_default_na=True, **kw)


def col(df, name):
    return df[name] if name in df.columns else pd.Series([np.nan] * len(df), index=df.index)


# 1. Spine
my = rd(FIN / "MyDatabase.csv")
my.columns = [c.strip() for c in my.columns]
my = my[[c for c in my.columns if c and not c.lower().startswith("unnamed")]]
my["source"] = my["NewID"].str.split("-").str[0]
print(f"[spine] rows={len(my)} by source={my['source'].value_counts().to_dict()}")

# 1b. Exclude entries whose source label is not a stoichiometric formula.
#     Acronyms (LFP, LLZO, PEO) and oxidation-state notation (Cu(II), FeII) carry no composition
#     information; the permissive formula parser used at matching time had coerced them into
#     unrelated Materials Project entries. The same rule now guards the matcher itself
#     (03_matching/src/matching.py::is_stoichiometric_label); it is applied here as well so the
#     published tables are correct without re-running the Materials Project queries.
sys.path.insert(0, str(PKG / "03_matching"))
from src.matching import is_stoichiometric_label  # noqa: E402

ok = my["ChemFormula"].astype(str).map(is_stoichiometric_label)
excluded = my.loc[~ok, ["NewID", "ID", "source", "ChemFormula", "best_mpid", "Tier"]].copy()
excluded["reason"] = "label_not_stoichiometric"
excluded.to_csv(INT / "excluded_entries.csv", index=False, encoding="utf-8")
my = my.loc[ok].reset_index(drop=True)
N = len(my)
print(f"[exclude] {len(excluded)} entries written to data/interim/excluded_entries.csv "
      f"({sorted(excluded['ChemFormula'].unique())}); retained rows={N}")

# 2. Match evidence
res_files = {"OBX": "NewObelixResult.csv", "LIV": "NewLiverpoolResult.csv", "ACS": "NewACSOmegaResult.csv"}
ev_cols = ["best_score", "best_reasons", "best_sg_relation", "best_spg_symbol",
           "best_spg_number", "best_crystal_system", "best_cif_tier", "best_deprecated", "candidates"]
frames = []
for src, fn in res_files.items():
    d = rd(INT / fn); d["source"] = src
    frames.append(d[["source", "ID", "best_mpid"] + [c for c in ev_cols if c in d.columns]].drop_duplicates(["source", "ID"]))
ev = pd.concat(frames, ignore_index=True).rename(columns={"best_mpid": "best_mpid_ev"})
m = my.merge(ev, on=["source", "ID"], how="left")
print(f"[evidence] match rate={m['best_score'].notna().mean():.3f} "
      f"best_mpid agreement={(m['best_mpid'].fillna('')==m['best_mpid_ev'].fillna('')).mean():.3f}")

# 3. Provenance
obx, acs, liv = rd(INT / "ObelixSGReady.csv"), rd(INT / "ACSOmegaSGReady.csv"), rd(INT / "LiverpoolSGReady.csv")
prov = pd.concat([
    pd.DataFrame({"source": "OBX", "ID": col(obx, "ID"), "prov_DOI": col(obx, "DOI"),
                  "reported_SG": col(obx, "Space group"), "ICSD_ID": col(obx, "ICSD ID"), "source_label": "OBELiX"}),
    pd.DataFrame({"source": "ACS", "ID": col(acs, "Column1"), "prov_DOI": col(acs, "DOI"),
                  "reported_SG": col(acs, "General SG"), "ICSD_ID": np.nan, "source_label": "Shon et al. (2023)"}),
    pd.DataFrame({"source": "LIV", "ID": col(liv, "ID"), "prov_DOI": np.nan,
                  "reported_SG": col(liv, "General SG"), "ICSD_ID": np.nan, "source_label": "Liverpool Ionics"}),
], ignore_index=True)
prov["ID"] = prov["ID"].astype(str).str.strip()
prov = prov.drop_duplicates(["source", "ID"])
m["ID"] = m["ID"].astype(str).str.strip()
m = m.merge(prov, on=["source", "ID"], how="left")
print("[provenance] DOI coverage by source=" +
      str(m.groupby("source")["prov_DOI"].apply(lambda s: round(s.notna().mean(), 3)).to_dict()))

# 4. Column order
ordered = ["NewID", "ID", "source_label", "ChemFormula", "Conductivity (S / cm)", "Temperature / C",
           "Family", "Tier", "best_mpid", "prov_DOI", "reported_SG", "ICSD_ID", "best_reasons",
           "best_sg_relation", "best_spg_symbol", "best_spg_number", "best_crystal_system",
           "best_cif_tier", "best_deprecated", "candidates"]
master = m[[c for c in ordered if c in m.columns]].copy()

# 5. Integrity
assert len(master) == N, f"row count changed: {len(master)} != {N}"
assert (master["NewID"].values == my["NewID"].values).all(), "spine identity changed"
print(f"[verify] master rows={len(master)} tiers={master['Tier'].value_counts().to_dict()}")

# 6. Write
FIN.mkdir(parents=True, exist_ok=True)
master.to_csv(FIN / "sse_conductivity_master.csv", index=False, encoding="utf-8")
slim = my[["NewID", "ID", "ChemFormula", "best_mpid", "Conductivity (S / cm)", "Temperature / C", "Family", "Tier"]].copy()
slim.to_csv(FIN / "sse_conductivity_slim.csv", index=False, encoding="utf-8")
print(f"[write] sse_conductivity_master.csv ({master.shape[0]}x{master.shape[1]}) ; sse_conductivity_slim.csv ({slim.shape[0]}x{slim.shape[1]})")
