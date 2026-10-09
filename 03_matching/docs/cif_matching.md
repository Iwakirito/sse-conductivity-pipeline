# CIF Matching Tiers

Comparator
- Uses `pymatgen.analysis.structure_matcher.StructureMatcher` to determine geometric equivalence.
- Species comparator is strict (element-wise); we do not use anonymous comparators.

Tiers and Parameters
- strict (score 90): `ltol=0.2`, `stol=0.3`, `angle_tol=5`, `primitive_cell=True`, `attempt_supercell=False`, `allow_subset=False`
- medium (score 85): `ltol=0.3`, `stol=0.5`, `angle_tol=7`, `attempt_supercell=True`
- loose (score 80): `ltol=0.4`, `stol=0.7`, `angle_tol=10`, `attempt_supercell=True`, `allow_subset=True`
- very_loose (score 75): `ltol=0.5`, `stol=0.9`, `angle_tol=15`, `attempt_supercell=True`, `allow_subset=True`

Why Tiered
- Real-world CIFs are often noisy (randomized coordinates, cell perturbations).
- Tiering exposes when a match becomes possible and ties confidence to the tolerated deviation.

Sweep vs Fixed Tier
- Sweep: try strict → very_loose and use the first tier that matches; notes record the tier and parameters.
- Fixed tier: use when you want consistent strictness (e.g., audits).

Failure Modes and Mitigations
- No match at any tier: either a true mismatch or extreme perturbation — rely on formula+SG evidence and manual review.
- False positives at very_loose: check that formula and crystal system also align; inspect tier and parameters in notes.
- Supercells: `attempt_supercell` handles some commensurate cases in medium+ tiers.

Extending/Tuning
- You can add intermediate tiers (e.g., `ltol=0.35`) or log RMS displacement if you need finer control.
- Keep scores monotonic with strictness to preserve ranking semantics.

Code References
- Tier config and matching: `src/matching.py`
- CLI flags: `tests/play_matching.py`, `tools/batch_match.py`
