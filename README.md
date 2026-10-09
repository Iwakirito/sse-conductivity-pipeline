# SSE Conductivity Dataset & Pipeline

A harmonized, structure-anchored dataset of experimentally reported **solid-state
electrolyte (SSE) ionic conductivities**, linked to the **Materials Project (MP)**
with a transparent, tiered confidence scheme — plus the full pipeline that builds it
and a retrieval-augmented (RAG) query demo.

The dataset merges three open experimental sources — **OBELiX**, **Liverpool Ionics**,
and **Shon et al. (2023)** — cleans and normalizes them, and links each retained
conductivity measurement to a unique MP identifier with an explicit evidence **Tier**.

## Dataset at a glance

- **3106** conductivity measurements -> **303** distinct Materials Project entries
- Evidence tiers: **T1 = 64**, **T2 = 388**, **T3 = 102** (high-confidence, 554 total) and **T4 = 2552** (formula-level)
- Sources: Shon et al. 2820, Liverpool 148, OBELiX 138

Published tables live in `data/final/`:
- `sse_conductivity_master.csv` — fully-provenanced master (20 columns: identifiers, conductivity,
  temperature, family, tier, MP id, DOI, reported space group, ICSD, and the MP match evidence).
- `sse_conductivity_slim.csv` — analysis/ML-ready slim table (8 columns).

See **[DATA_DICTIONARY.md](DATA_DICTIONARY.md)** for every column.

## Repository layout / pipeline run order

| Stage | Folder | What it does |
|------|--------|--------------|
| 1 | `01_cleaning/`  | Clean & normalize raw conductivity strings -> single Float64 value |
| 2 | `02_merging/`   | Harmonize the three sources onto the common 7-field schema |
| 3 | `03_matching/`  | Link each entry to Materials Project and assign an evidence Tier |
| – | `build_master_dataset.py` | Join final tiers + provenance + match evidence -> `data/final/` |
| 4 | `04_analysis/`  | Statistics & figures (see folder README) |
| 5 | `05_rag/`       | Optional natural-language RAG query demo over the dataset |

`data/` holds `raw/` (original source inputs), `interim/` (cleaned, space-group-ready,
and per-source MP match outputs), and `final/` (the published tables above).

## Evidence tiers

- **T1 — Geometric isomorphism:** the experimental CIF matches an MP structure (pymatgen `StructureMatcher`).
- **T2 — Formula + exact space group.**
- **T3 — Formula + same crystal system.**
- **T4 — Formula only:** a compositionally identical MP entry exists, without symmetry/structure confirmation. Treat as a *formula-level* link rather than a polymorph-resolved structural assignment.
- *(An identifier route — ICSD/DOI — was attempted first but yielded no unambiguous links in these sources; it is retained in the code for generality.)*

## Quickstart

```bash
# 1. Environment (conda)
conda env create -f environment.yml && conda activate sse-pipeline

# 2. Materials Project access (for the matching stage)
export MP_API_KEY=your_key_here

# 3. Run matching for a source (example)
python 03_matching/tools/batch_match.py \
    --csv data/interim/ObelixSGReady.csv \
    --out data/interim/NewObelixResult.csv \
    --matcher-sweep --use-structure-sg

# 4. Rebuild the published dataset from pipeline outputs
python build_master_dataset.py
```

The RAG demo (`05_rag/`) additionally requires a local [Ollama](https://ollama.com/)
server (`llama3.1:8b`) and a FAISS index (`05_rag/artifacts/`); see `05_rag/RAG_CONFIG.md`.

## Source versions

The three source datasets were used as publicly released by their authors, and Materials Project
queries were performed through `mp-api` (database release v2025.09.25). `data/final/mpid_map.csv`
lists, for every anchor, the numeric identifier used in the dataset alongside its current
alphabetic Materials Project identifier.

## Associated manuscript

This repository accompanies a manuscript currently under review. Citation details
will be added here upon acceptance.

## License

Code: MIT (see [LICENSE](LICENSE)). Data (`data/`): CC-BY-4.0. Source datasets
(`data/raw/`) originate from their respective open publications (OBELiX; Liverpool
Ionics; Shon et al. 2023) and remain subject to the licenses under which they were
originally released — see DATA_DICTIONARY.md and the manuscript for full attribution.
