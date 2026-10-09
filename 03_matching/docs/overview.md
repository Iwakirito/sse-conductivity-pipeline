# Overview

Purpose
- Map Obelix CSV rows + CIFs to Materials Project materials with high recall and transparent ranking.
- Keep the workflow explainable and tunable for research, not just ML competitions.

Guiding Principles
- Robustness: normalize inputs (reduced formula, SG symbol/system), handle missing/"noisy" fields.
- Transparency: every candidate carries a reason, score, and notes; aggregate view merges signals per MPID.
- Layered search: strongest linkage first (ICSD), then symmetry, then geometry, then composition.
- Non-destructive: tools read inputs and write new artifacts; originals remain untouched.

Success Criteria
- For known exemplars (e.g., Li7BiO6 → mp-38487), best candidate appears with a clear justification.
- On broader sets, the top few candidates include the true MPID with reasonable scores.
- Rationale is auditable: users can see why something matched or did not.

Non-Goals
- Perfect automation of ambiguous cases (e.g., polymorphs) — we surface evidence to aid expert review.
- Modeling structure-property predictions — this pipeline focuses on mapping/identity.

Executive Summary (for domain scientists)
- What: We identify the same material in MP for each Obelix row using four increasingly permissive checks.
- Why this order: We prefer direct identity links (ICSD), then crystallographic agreement (space group), then geometric equivalence (CIF), then composition-only when needed.
- Trust model: Each candidate shows why it matched and is scored by evidence strength; deprecated MP records are allowed but slightly penalized.
- Outcome: One consolidated, ranked list per row that is easy to audit.

Key Design Choices (non-programming)
- Reduced formula matching: prevents false negatives due to element orderings (Li7BiO6 vs BiLi7O6).
- Space-group normalization: avoids formatting variation (“P -1” vs “P-1”) and uses crystal system as a reasonable fallback.
- Tiered CIF matching: handles randomized/noisy CIFs by gradually relaxing tolerances and reporting which tier matched.
- Deprecated handling: include both current and deprecated to avoid missing legitimate entries; prefer current ones via a small scoring penalty.

Assumptions and Limits
- Dataset IDs are unique after merge and map 1:1 to CIF files.
- CSV SG may be incomplete or noisy; crystal-system checks and structure-derived SG mitigate this.
- CIFs may be perturbed; a very loose tier increases recall but can risk false positives — always review reasons and tiers.
