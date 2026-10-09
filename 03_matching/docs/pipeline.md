# Matching Pipeline

Stage Order
- ICSD → DOI → Formula + Space Group → CIF → Formula-only
- Default behavior: return first non-empty stage (the CLI can `--show-all` for inspection)

Normalization
- Composition: `pymatgen.Composition(reduced_string).reduced_formula`
- SG symbol: remove spaces, normalize hyphens; compare by number when available
- Crystal system: map SG number → system (triclinic…cubic); normalize enum/string to lowercase

Stages
- ICSD (reason: `icsd_match`, score 100)
  - Why first: strongest identity linkage
  - Behavior: try `deprecated=False`, then include both (`None`)

- DOI (reason: `doi_match`, score 100)
  - Why: bibliographic link is as strong as ICSD when references align
  - Behavior: try `deprecated=False`, then include both (`None`); normalizes DOI strings and matches across heterogeneous CSV columns (`DOI`, `source`, etc.)

- Formula + SG (reasons: `formula+sg` or `formula+sg_system`, score 70 or 60)
  - Exact SG match: number or normalized symbol
  - Same system fallback: e.g., P1 vs P-1 → triclinic
  - Option: infer SG from MP structures for reliability (`--use-structure-sg`)

- CIF (reason: `cif_match`, score by tier)
  - Tiers: strict 90 | medium 85 | loose 80 | very_loose 75
  - Returns matches from the first tier that fits (when sweeping)
  - Notes include tier and tolerance parameters

- Formula-only (reason: `formula_only`, score by SG relationship)
  - Exact number 65 | exact symbol 63 | same system 55 | mismatch 40
  - Fallback to chemsys search if direct formula yields none; filter by reduced composition equality

Aggregation
- Candidates are merged per MPID with:
  - best score across stages
  - union of reasons
  - symmetry fields (SG, system) and CIF tier in notes
- Ranking: non-deprecated first, then score desc, then MPID

Early Exit vs Inspection
- Programmatic: stop at first non-empty stage (higher precision)
- Interactive: `--show-all` to display evidence from each stage

