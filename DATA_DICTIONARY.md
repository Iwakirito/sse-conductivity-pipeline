# Data Dictionary

## `data/final/sse_conductivity_master.csv` (3106 rows x 20 columns)

One row per retained experimental conductivity measurement. The final tiered table is
the spine; provenance and MP match evidence are joined on (source, ID).

| Column | Description |
|--------|-------------|
| `NewID` | Globally unique ID: `[SRC]-[OriginalID]` (SRC = OBX / LIV / ACS). |
| `ID` | Original identifier in the source database. |
| `source_label` | Human-readable source: OBELiX, Liverpool Ionics, or Shon et al. (2023). |
| `ChemFormula` | Chemical formula of the material. |
| `Conductivity (S / cm)` | Ionic conductivity, normalized to a single value (S/cm). |
| `Temperature / C` | Measurement temperature (°C) where reported; blank otherwise (~5% coverage). |
| `Family` | Structural family (e.g. Garnet, NASICON-like); "Unassigned" where the source gave none. |
| `Tier` | Evidence tier of the MP linkage: T1 > T2 > T3 > T4 (see README). |
| `best_mpid` | Selected Materials Project identifier (the "structural anchor"). |
| `prov_DOI` | DOI of the primary experimental reference (present for OBELiX & Shon; absent for Liverpool). |
| `reported_SG` | Space group reported/inferred from the source. |
| `ICSD_ID` | ICSD accession from the source, where available (mainly OBELiX). |
| `best_reasons` | Evidence that produced the match (e.g. `cif_match`, `formula+sg`, `formula_only`). |
| `best_sg_relation` | Space-group relation to the MP candidate: exact / same_system / mismatch. |
| `best_spg_symbol` | Space-group symbol of the chosen MP entry. |
| `best_spg_number` | Space-group number of the chosen MP entry. |
| `best_crystal_system` | Crystal system of the chosen MP entry. |
| `best_cif_tier` | StructureMatcher tolerance tier at which a CIF match was found (if any). |
| `best_deprecated` | Whether the chosen MP entry is deprecated in MP. |
| `candidates` | JSON list of all considered MP candidates with their evidence (full audit trail). |

### Coverage / known limitations
- **DOI:** present for ~87% of rows (OBELiX + Shon); the Liverpool source file carries no per-entry DOI.
- **Temperature:** reported for ~5% of rows; concentrated near room temperature.
- **Tier 4 (≈82% of rows):** formula-level link only — `best_mpid` is a compositionally
  identical MP entry, not a structure-resolved polymorph assignment.

## `data/final/sse_conductivity_slim.csv` (3106 rows x 8 columns)
Analysis/ML-ready subset: `NewID, ID, ChemFormula, best_mpid, Conductivity (S / cm), Temperature / C, Family, Tier`.

## `data/final/mpid_map.csv` (303 rows x 5 columns)

Materials Project now issues alphabetic identifiers alongside the numeric ones. The numeric `best_mpid`
values used throughout this dataset remain valid and resolvable; this table lists, for each of the 303
anchors, the corresponding alphabetic identifier together with the formula and symmetry reported by
Materials Project for that entry (release v2026.04.13).

## `data/interim/excluded_entries.csv` (17 rows)

Source entries excluded at assembly because their label is not a stoichiometric formula (acronyms such
as LFP or LLZO; oxidation-state notation such as Cu(II)). See `build_master_dataset.py`, step 1b.
