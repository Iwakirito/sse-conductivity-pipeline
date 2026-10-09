# CLI Usage

## Single-ID Exploration (`tests/play_matching.py`)

Use this script when you want to inspect how one row flows through each matching stage.

### Required arguments
- `--csv PATH` – dataset CSV to load (merged Obelix export or any compatible file).
- `--id ROW_ID` – identifier to look up (e.g. `jqc`).

### Helpful optional arguments
- `--row-id-field NAME` – column that holds the IDs (default: `id`).
- `--split LABEL` – legacy train/test label used only when CIFs live in split folders.
- `--api-key KEY` – Materials Project API key; otherwise the script reads `MP_API_KEY`/`MAPI_KEY` from the environment.
- `--show-all` – do not exit after the first successful stage; show every stage outcome.
- `--debug` – echo whether an API key was detected and how many candidates came back from a quick formula query.

### Stage toggles
- `--no-icsd` – skip the ICSD linking stage.
- `--no-formula-sg` – skip formula + space-group filtering.
- `--no-cif` – skip CIF structure matching.
- `--no-fallback` – skip the formula-only fallback.
- `--no-deprecated` – drop deprecated MP entries from candidate lists (ICSD still retries with and without).

### CIF / symmetry controls
- `--matcher-tier {strict,medium,loose,very_loose}` – pick one tolerance tier for the CIF StructureMatcher.
- `--matcher-loose` – shorthand for `--matcher-tier loose`.
- `--matcher-sweep` – try tiers in order until a match is found.
- `--use-structure-sg` – enrich rows with symmetry derived from MP structures before SG comparisons.

### Output interpretation
The script prints each stage followed by an **Aggregate candidates** table:
- score (best across stages), reasons hit, space-group relation (exact/same_system/mismatch),
- space-group symbol/number, crystal system, CIF tier (or "no" if none matched),
- deprecated flag so you can prioritize current MP records.

## Batch Matching (`tools/batch_match.py`)

Run this to score every row in a dataset and save the aggregated results to disk.

### Required arguments
- `--csv PATH` – dataset to consume (e.g. `data/ObelixData.csv`).
- `--out PATH` – destination for the results CSV. Pick any filename such as `data/ObelixMatches.csv` or `data/run_2025-03-01.csv`.

### Dataset selection
- `--row-id-field NAME` – force the ID column name if auto-detection struggles.
- `--ids-file FILE` – process only IDs listed in `FILE` (one per line).
- `--limit N` – stop after `N` rows; handy for smoke tests or iterative debugging.

### Matching behaviour
- `--use-structure-sg` – populate symmetry from downloaded MP structures before scoring.
- `--no-deprecated` – exclude deprecated MP entries during formula-only fallbacks.
- `--matcher-tier {strict,medium,loose,very_loose}` – use a single CIF tolerance tier.
- `--matcher-loose` – alias for `--matcher-tier loose`.
- `--matcher-sweep` – try each tier in order until a CIF match is produced (overrides the single-tier options).

### Credentials & logging
- `--api-key KEY` – explicit MP API key; otherwise reads `MP_API_KEY`/`MAPI_KEY`.
- `--debug` – print per-row progress and any caught exceptions while the batch runs.

### Output columns
The written CSV contains `best_*` summary columns plus a JSON-encoded `candidates` list with every ranked MPID (score, reasons, SG relation, symmetry info, CIF tier, deprecated flag).

### Usage patterns
```powershell
# Full run with the default ladder of CIF tolerances
python tools\batch_match.py --csv data\ObelixData.csv --out data\ObelixMatches.csv --matcher-sweep --use-structure-sg

# Smoke test: first 50 rows, verbose logging, loose matcher only
python tools\batch_match.py --csv data\ObelixData.csv --out data\smoke.csv --limit 50 --debug --matcher-tier loose

# Focus on selected IDs listed in ids.txt
python tools\batch_match.py --csv data\ObelixData.csv --out data\subset.csv --ids-file ids.txt --matcher-sweep
```

## CIF Paths

- If the CSV has a `cif_path` column, both scripts use that path directly (absolute or relative to the CSV).
- Otherwise they first look for `data/cifs/<ID>.cif`, then fall back to legacy `data/<split>_cifs/**/<ID>.cif` when the `split` column is present.
