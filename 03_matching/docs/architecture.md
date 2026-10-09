# Architecture

Modules
- `src/materials_api.py`: Thin wrapper over `mp_api.MPRester` with:
  - `by_icsd(icsd_id, include_deprecated) -> list[mpid]`
  - `by_formula(formula, include_deprecated) -> list[MPDocumentSummary]`
  - `by_chemsys(elements, include_deprecated) -> list[MPDocumentSummary]`
  - `by_formula_sg(formula, spg_number, spg_symbol, include_deprecated) -> list[mpid]`
  - `structures_for(mpids) -> dict[mpid, Structure]`
  - Decision: prefer `mpr.materials.summary` if available; fall back to `mpr.summary`.
  - Decision: symmetry parsed robustly from dict/attribute shapes; client-side filters for reliability.
  - Decision: wrap mp_api access so the rest of the matching code stays decoupled and easy to mock or swap.
  - Decision: normalize symmetry regardless of whether mp_api returns dicts or Pydantic models while the service migrates.

- `src/matching.py`: Matching filters + pipeline helpers:
  - Normalizers: `normalize_formula`, `normalize_spacegroup_symbol`, crystal system mapping
  - CIF path resolver: unified `cifs/` preferred; legacy split fallback
  - Filters: `filter_icsd`, `filter_formula_sg`, `filter_cif_match`, `filter_formula_only`
  - Tiered CIF matching ladder with per-tier tolerances and scores
  - Aggregation concept (used by CLI) merges reasons per MPID and keeps best score

- CLI tools:
  - `tests/play_matching.py`: Single-ID exploration; prints stage-by-stage and an aggregate table
  - `tools/batch_match.py`: Batch processor; writes one row per ID with `best_*` fields and a JSON `candidates` column
- `src/pipeline.py`: DataFrame/CSV utilities that apply `match_row` across a dataset and append `best_mpid` plus serialized `candidates` for downstream analysis.


Key Decisions
- Client-side SG filtering: avoids brittle nested-field server queries, and allows post-processing (exact vs same-system).
- Include-deprecated semantics: we pass `deprecated=None` to include both when maximizing recall; deprecated entries are penalized (-5) during scoring.
- Composition robustness: rely on `pymatgen.Composition` reduced formulas for equality, not string order.
- Structure-derived symmetry: optional enrichment using MP structures (and can be extended to CIF) to improve SG matching.





