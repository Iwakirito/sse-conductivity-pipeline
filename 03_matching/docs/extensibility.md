# Extensibility

Adding a new filter
- Where: `src/matching.py`
- Pattern:
  - Input: normalized row fields; `MaterialsProjectAPI` for data access
  - Output: list of `MatchCandidate(mpid, reason, score, notes)`
- Keep it pure (no I/O); let CLIs orchestrate and print

Scoring a new filter
- Choose a weight consistent with the existing hierarchy
- Document rationale in `docs/scoring.md`
- Annotate notes with any qualifiers you’ll need later (e.g., tolerances, property ranges)

Modifying CIF tiers
- Edit tier params and scores in `src/matching.py`
- Keep monotonic scores: stricter tiers must score higher
- Update `docs/cif_matching.md` to match

Alternate symmetry sources
- You can add CIF-derived SG via `pymatgen.symmetry.SpacegroupAnalyzer` and feed it into SG-based filters
- Be explicit in notes when SG came from CIF vs MP vs CSV

New datasets
- Map their columns to the core fields used here (`ID`, `ICSD ID`, `Reduced Composition`, `Space group #`, `Space group`, `cif_path`)
- Ensure a unified `cifs/` folder or populate `cif_path`

Testing & Safety
- Start with `tests/play_matching.py` for a few rows to verify behavior
- For batch changes, run `tools/batch_match.py --limit 50 --debug` before full runs

