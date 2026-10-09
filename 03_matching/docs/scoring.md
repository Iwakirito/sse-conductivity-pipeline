# Scoring Model

Goals
- Reflect evidence strength: ICSD > geometry > symmetry > composition
- Penalize deprecated entries slightly while allowing them as recall boosters
- Produce stable, interpretable rankings across rows

Weights (current)
- ICSD: `icsd_match` → 100
- DOI: `doi_match` → 100
- CIF: `cif_match` → strict 90 | medium 85 | loose 80 | very_loose 75
- Formula + SG: `formula+sg` (exact) 70 | `formula+sg_system` 60
- Formula-only: `formula_only`
  - exact SG number 65
  - exact SG symbol 63
  - same crystal system 55
  - mismatch/unknown 40
- Deprecated penalty: -5 (applied when a candidate MP doc is marked deprecated)

Stage precedence vs within-stage score
- The pipeline short-circuits by stage for programmatic matching — earlier stages are trusted more than later ones.
- When presenting candidates (interactive and batch), we keep the best score per MPID across stages and merge reasons.

Tie-breaking
- Prefer non-deprecated entries
- Then higher score
- Then lexicographic MPID (stable ordering)

Rationale & Nuances
- ICSD/DOI are direct identity or bibliographic links and thus the strongest signals.
- CIF geometry is strong evidence; tiering helps handle noisy/randomized CIFs and explicitly trades recall vs precision.
- SG exact > same-system: identical space groups are better than just matching crystal family.
- Formula-only is weakest; SG alignment boosts are modest to avoid overfitting noisy SG fields.
- Deprecated demotion: keeps knowledge of superseded entries while favoring current ones when tied.

Examples
- Li7BiO6 (jqc):
  - CSV SG P-1 vs MP P1 → same-system (triclinic) → `formula+sg_system` 60; CIF may not match randomized files
  - Aggregate ranks mp-38487 highest due to symmetry alignment and non-deprecated status
- LiGaBr4 (be9):
  - Exact SG number (14) → `formula+sg` 70; CIF matches at strict tier → 90, becoming the top signal

Calibration & Future Work
- We can tune tier weights and SG boosts based on validation sets.
- Optional: track a continuous geometry similarity measure and map to finer-grained scores.

