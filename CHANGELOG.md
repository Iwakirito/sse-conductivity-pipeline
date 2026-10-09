# Changelog

## v1.0.0 — 2026-10

First public release.

- Dataset: 3106 conductivity measurements linked to 303 Materials Project entries
  (T1 64 / T2 388 / T3 102 / T4 2552).
- `03_matching/src/matching.py`: added `is_stoichiometric_label()`; the batch matcher now
  skips source labels that are acronyms (e.g. LFP, LLZO) or oxidation-state notation
  (e.g. Cu(II)) instead of passing them to the permissive formula parser.
- `build_master_dataset.py`: applies the same rule at assembly and writes the excluded
  entries to `data/interim/excluded_entries.csv` (17 entries, all from Shon et al. 2023).
- `04_analysis/make_figures.py`: reproducible generation of the aggregate figures.
- `data/final/mpid_map.csv`: numeric -> alphabetic Materials Project identifier map
  (Materials Project release v2026.04.13).
