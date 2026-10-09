# Materials Project Integration

Authentication
- API key: set `MP_API_KEY` (or `MAPI_KEY`) in your environment, or pass `--api-key` to CLIs.
- Sanity check: count Li7BiO6 docs via `MPRester.materials.summary.search`.

Routes & Compatibility
- Prefer `MPRester.materials.summary` (new) and fall back to `MPRester.summary` (old) to avoid deprecation warnings.
- Fields requested:
  - `material_id`, `formula_pretty`, `symmetry` (space group + crystal system), `deprecated` (when available)

Symmetry Extraction
- Summary docs vary (dict-like vs attribute-like). We extract from both safely.
- We normalize:
  - SG symbol: remove spaces, normalize hyphens
  - Crystal system: enum/string → lowercase string

Deprecated Semantics
- Query param `deprecated`:
  - `False`: only current docs
  - `True`: only deprecated docs
  - `None`: include both (used for recall during fallbacks)
- Scoring penalty: -5 for per-document deprecated candidates.

ICSD Linking
- We search summaries and filter client-side by `database_IDs.icsd` when present; server-side filters vary across mp-api versions.
- Coverage caveat: Not all MP entries expose ICSD links; hence additional stages.

Error Handling
- Network/API errors return empty lists in wrappers (non-fatal); CLIs surface “no candidates” with debug options.

Code References
- Wrapper: `src/materials_api.py`
- Usage: `src/matching.py`, `tests/play_matching.py`, `tools/batch_match.py`
