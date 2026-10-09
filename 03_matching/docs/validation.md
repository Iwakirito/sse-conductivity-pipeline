# Validation

Purpose
- Demonstrate that top candidates are plausible and rationale is transparent.

Spot Checks
- Known exemplar: `ID=jqc` → Li7BiO6 → top candidate mp-38487 with `formula+sg_system` and non-deprecated.
- Strict CIF success: `ID=be9` → LiGaBr4 → exact SG and `cif_match` at strict tier.

Procedure
- Interactive:
  - `python tests/play_matching.py --csv data/ObelixData.csv --id <ID> --show-all --matcher-sweep --use-structure-sg`
  - Review aggregate table: score, reasons, SG relation, CIF tier, deprecated.
- Batch:
  - `python tools/batch_match.py --csv data/ObelixData.csv --out data/ObelixMatches.csv --matcher-sweep --use-structure-sg --debug`
  - Pick a descriptive filename when saving (example above writes ObelixMatches.csv).
  - Sample random subset; compare best_mpid vs MP UI; log disagreements and inspect reasons.

Metrics (optional)
- Top-1 agreement on a labeled subset
- Top-k recall (k=3 or 5)
- Coverage of CIF tiers (how often strict vs loose)

Interpreting “no CIF match”
- If formula+SG (exact or same_system) is present and non-deprecated, confidence is often sufficient.
- If only formula-only mismatches appear, defer to expert review.

