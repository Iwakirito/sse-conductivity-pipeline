# MP Matching Pipeline — Documentation

This documentation explains the design, decisions, and usage of the matching pipeline that maps Obelix dataset entries (CSV + CIF) to Materials Project (MP) materials.

Who this helps
- Domain scientists: Understand the process and why it’s trustworthy without reading code.
- Engineers: Learn the minimal APIs, flags, and code boundaries to operate and extend safely.

Quick Links
- Overview: ./overview.md
- Data Layout: ./data.md
- Architecture: ./architecture.md
- Pipeline: ./pipeline.md
- Scoring Model: ./scoring.md
- CIF Matching Tiers: ./cif_matching.md
- MP Integration: ./mp_integration.md
- CLI Usage: ./cli.md
- Troubleshooting: ./troubleshooting.md
- Validation: ./validation.md
- Extensibility: ./extensibility.md
- Glossary: ./glossary.md

Quickstart
- Single ID exploration (unified dataset):
  - `python tests/play_matching.py --csv data/ObelixData.csv --id <ID> --show-all --matcher-sweep --use-structure-sg`
- Batch matching (writes results CSV):
  - `python tools/batch_match.py --csv data/ObelixData.csv --out data/ObelixMatches.csv --matcher-sweep --use-structure-sg`

Two tracks
- Scientist track: Read Overview → Pipeline → Scoring. Skim CIF Matching and MP Integration for nuance.
- Engineer track: Read Architecture → CLI → Troubleshooting. Skim Data and Extensibility.

Prerequisites
- Python environment with: `mp-api`, `pymatgen`, `pandas`
- Materials Project API key in `MP_API_KEY` (or pass `--api-key`)
