# Troubleshooting

No candidates returned
- Check API key: `echo $env:MP_API_KEY` (PowerShell). Use `--api-key` if needed.
- Use `--debug` to print by-formula counts (should be > 0 for common formulas).
- Ensure packages: `mp-api`, `pymatgen`, `pandas` installed in the active env.

401 Invalid authentication
- You likely passed a key as an env var name instead of the value.
- Set for session: `$env:MP_API_KEY="<key>" ; $env:MAPI_KEY=$env:MP_API_KEY`
- Rotate exposed keys in your MP account if a key was shared.

CIF path not found
- With unified data: file should be at `data/cifs/<ID>.cif` (or use `cif_path` column).
- Legacy: ensure `--split` is set and the CIF is under `data/<split>_cifs/**/<ID>.cif`.

SG mismatch confusion
- Symbols are normalized (“P -1” ~ “P-1”). P1 vs P-1 are both triclinic; that is treated as `same_system`.
- Enable `--use-structure-sg` to enrich MP symmetry and improve SG comparisons.

CIF match still fails
- Try `--matcher-sweep` to relax tolerances tier by tier.
- If still none, rely on symmetry/ICSD evidence and review candidates.

Batch run issues
- Use `--ids-file` to isolate problematic rows.
- `--debug` logs each ID processed and errors; results file includes an `error` field per row if captured.

Serialization errors
- Notes are normalized to strings where needed; CLIs use `default=str` when JSON-encoding.

