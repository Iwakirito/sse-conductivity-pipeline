# Data Layout

Merged Dataset
- CSV: `data/ObelixData.csv` (unified from train/test)
- CIFs: `data/cifs/<ID>.cif`
- Optional CSV column: `cif_path` (relative to CSV or absolute) overrides path inference.

Core Columns (consumed by the pipeline)
- `ID`: unique identifier (string). Auto-detected if named differently.
- `ICSD ID`: nullable integer (pandas `Int64`). Used for direct ICSD linkage.
- `Reduced Composition`: string. Parsed via `pymatgen.Composition` to a reduced formula.
- `Space group #`: optional integer. If present, preferred for exact SG checks.
- `Space group`: optional string. Normalized (remove spaces, unify hyphens) for symbol checks.
- `cif_path`: optional string. If present, used directly by CLI and resolvers.
- `split`: optional string. Legacy (“train”/“test”); only used if unified CIFs are not present.

CIF Resolution Order
- If `cif_path` exists in the row, use it.
- Else, look for `data/cifs/<ID>.cif` (recursive search allowed).
- Else, legacy fallback: `data/<split>_cifs/**/<ID>.cif` if `split` is present.

Schema Notes
- Merging aligns the union of columns; missing values are allowed.
- Duplicate `ID` across original train/test should be resolved during merge (tool enforced); the unified CSV assumes uniqueness.

