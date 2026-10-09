from __future__ import annotations

"""
Matching filters and row-by-row pipeline for the Obelix dataset.

What: Implements a sequence of matching strategies:
1) ICSD ID match (when present)
2) DOI bibliographic match
3) Formula + space group match
4) CIF structure match vs MP structures
5) Formula-only fallback

Why: MP does not always expose ICSD links, so a layered approach improves
recall while keeping precision via structure matching and symmetry filters.
Each function is small, explicit, and documented for maintainability.
"""

from collections.abc import Iterable as IterableABC
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

try:
    from pymatgen.core import Composition, Structure  # type: ignore
    from pymatgen.analysis.structure_matcher import StructureMatcher  # type: ignore
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    Composition = None  # type: ignore
    Structure = None  # type: ignore
    StructureMatcher = None  # type: ignore
    SpacegroupAnalyzer = None  # type: ignore

from .materials_api import MaterialsProjectAPI, MPDocumentSummary

# -------- CIF tiered matching configuration -------- #

# Ordered tiers from strictest to loosest
CIF_MATCH_TIERS: List[str] = ["strict", "medium", "loose", "very_loose"]

CIF_TIER_PARAMS: Dict[str, Dict[str, Any]] = {
    "strict": {
        "ltol": 0.2,
        "stol": 0.3,
        "angle_tol": 5,
        "primitive_cell": True,
        "attempt_supercell": False,
        "allow_subset": False,
    },
    "medium": {
        "ltol": 0.3,
        "stol": 0.5,
        "angle_tol": 7,
        "primitive_cell": True,
        "attempt_supercell": True,
        "allow_subset": False,
    },
    "loose": {
        "ltol": 0.4,
        "stol": 0.7,
        "angle_tol": 10,
        "primitive_cell": True,
        "attempt_supercell": True,
        "allow_subset": True,
    },
    "very_loose": {
        "ltol": 0.5,
        "stol": 0.9,
        "angle_tol": 15,
        "primitive_cell": True,
        "attempt_supercell": True,
        "allow_subset": True,
    },
}

CIF_TIER_SCORES: Dict[str, int] = {
    "strict": 90,
    "medium": 85,
    "loose": 80,
    "very_loose": 75,
}


# -------- Data containers -------- #


@dataclass
class MatchCandidate:
    """A single candidate result with provenance.

    What: Minimal info for ranking and auditing.
    Why: Keep pipeline transparent; enable later scoring tweaks.
    """

    mpid: str
    reason: str  # e.g., "icsd_match", "formula+sg", "cif_match", "formula_only"
    score: int
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchResult:
    """Aggregated result for a single row."""

    best_mpid: Optional[str]
    candidates: List[MatchCandidate]


# -------- Normalization helpers -------- #

DOI_REGEX = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


_ELEMENTS = set("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr
Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re
Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr""".split())
_OXIDATION_STATE_RE = re.compile(r"\((?:I|II|III|IV|V|VI|VII)\)|(?<=[A-Za-z])(?:II|III|IV)$")
_ELEMENT_TOKEN_RE = re.compile(r"[A-Z][a-z]?")


def is_stoichiometric_label(label: str) -> bool:
    """
    Return True only if `label` can be read as a stoichiometric formula.

    What: Rejects source labels that are acronyms (LFP, LLZO, PEO), oxidation-state
          notation (Cu(II), FeII) or otherwise contain tokens that are not element symbols.
    Why:  pymatgen's Composition parser is permissive: "Cu(II)" parses as CuI2 and acronyms
          can be coerced into unrelated element sets, producing confident but wrong MP links.
          Such labels carry no composition information and must not enter the matcher.
    """
    text = (label or "").strip()
    if not text:
        return False
    if _OXIDATION_STATE_RE.search(text):
        return False
    letters_only = re.sub(r"[^A-Za-z]", "", text)
    if letters_only.isupper() and len(letters_only) >= 3 and not any(ch.isdigit() for ch in text):
        # e.g. LFP, LLZO, PEO, LATP — all-caps acronym with no stoichiometry
        return False
    tokens = _ELEMENT_TOKEN_RE.findall(re.sub(r"[\(\)\[\]\.\d\s·,+-]", "", text))
    if not tokens or any(t not in _ELEMENTS for t in tokens):
        return False
    return True


def normalize_formula(reduced_composition_str: str) -> str:
    """
    Normalize a composition string to a reduced formula using pymatgen.

    What: Converts arbitrary representations to a canonical reduced formula.
    Why: Ensures robust comparison even when element order/format differs.
    """
    if Composition is None:  # pragma: no cover - environment-dependent
        # Fallback: best-effort whitespace strip
        return (reduced_composition_str or "").strip()
    comp = Composition(str(reduced_composition_str))
    return comp.reduced_formula


def normalize_spacegroup_symbol(symbol: Optional[str]) -> Optional[str]:
    """
    Normalize common variations in space group symbols (spacing, hyphens).

    What: Removes spaces and normalizes hyphens.
    Why: CSVs and services differ in formatting; this reduces spurious mismatches.
    """
    if not symbol:
        return None
    s = str(symbol)
    s = s.replace(" ", "")
    s = s.replace("−", "-")  # normalize unicode minus to ASCII hyphen
    s = s.replace("−", "-")  # unicode minus to hyphen
    s = s.replace("_", "-")
    return s


def normalize_doi(value: Any) -> Optional[str]:
    """
    Normalize DOI strings by stripping prefixes and extracting canonical tokens.

    Accepts raw strings (including URLs like https://doi.org/... or prefixed
    forms such as doi:10.xxxx). Returns a lowercase DOI or None when parsing fails.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    lowered = s.lower()
    if lowered.startswith("doi:"):
        s = s[4:]
        lowered = s.lower()
    if "doi.org/" in lowered:
        idx = lowered.index("doi.org/") + len("doi.org/")
        s = s[idx:]
    s = s.strip()
    match = DOI_REGEX.search(s)
    if match:
        return match.group(0).rstrip(".").lower()
    if s.lower().startswith("10."):
        return s.lower().rstrip(".")
    return None


def extract_row_doi(row: Mapping[str, Any]) -> Optional[str]:
    """
    Extract and normalize a DOI from heterogeneous dataset schemas.

    Looks for columns containing "doi" (case-insensitive) as well as the
    Liverpool-specific "source" field.
    """
    candidate_values: List[Any] = []
    for key, value in row.items():
        key_str = str(key).strip().lower()
        if "doi" in key_str or key_str == "source":
            candidate_values.append(value)
    for val in candidate_values:
        doi = normalize_doi(val)
        if doi:
            return doi
    return None


def _ensure_list(value: Any) -> List[Any]:
    """
    Flatten iterables (excluding strings) into a list for downstream coercion.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, IterableABC):
        items: List[Any] = []
        for v in value:
            items.extend(_ensure_list(v))
        return items
    return [value]


def _unique_preserve(seq: Iterable[Any], *, key=None) -> List[Any]:
    """
    Deduplicate while preserving order. Optional key function for comparisons.
    """
    seen: Set[Any] = set()
    out: List[Any] = []
    for item in seq:
        marker = key(item) if key else item
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _coerce_int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        s = str(value).strip()
        if s == "" or s.lower() == "nan":
            return None
        return int(float(s)) if "." in s else int(s)
    except Exception:
        return None


def _coerce_int_list(values: Any) -> List[int]:
    items = []
    for v in _ensure_list(values):
        n = _coerce_int_or_none(v)
        if n is not None:
            items.append(n)
    return _unique_preserve(items)


def _normalize_symbol_list(values: Any) -> List[str]:
    items = []
    for v in _ensure_list(values):
        sym = normalize_spacegroup_symbol(v)
        if sym:
            items.append(sym)
    return _unique_preserve(items, key=lambda s: s.lower())


def resolve_cif_path(
    row_id: str,
    split: Optional[str] = None,
    base_dir: Optional[Path] = None,
    cif_dir_map: Optional[Mapping[str, Path]] = None,
) -> Path:
    """
    Map a row id and split ("train" or "test") to a CIF path.

    What: Encodes the dataset's fixed layout (train_cifs/ and test_cifs/).
    Why: Centralize the mapping so callers don't sprinkle path logic.
    """
    base = base_dir or Path.cwd()
    # Prefer unified CIFs directory if present
    alt_folder = None
    if cif_dir_map and "unified" in cif_dir_map:
        alt_folder = Path(cif_dir_map["unified"])  # e.g., data/cifs
    else:
        alt_folder = (base / "cifs") if base else Path("cifs")

    if alt_folder and alt_folder.exists():
        alt_default = alt_folder / f"{row_id}.cif"
        if alt_default.exists():
            return alt_default
        try:
            for p in alt_folder.rglob(f"{row_id}.cif"):
                return p
        except Exception:
            pass

    # Otherwise, fall back to split-specific layout if a split was provided
    if split:
        if cif_dir_map and split in cif_dir_map:
            folder = Path(cif_dir_map[split])
        else:
            folder = (base / f"{split}_cifs") if base else Path(f"{split}_cifs")
        default = folder / f"{row_id}.cif"
        if default.exists():
            return default
        try:
            for p in folder.rglob(f"{row_id}.cif"):
                return p
        except Exception:
            pass

        return default

    # Last resort: return unified default path even if missing
    return (alt_folder / f"{row_id}.cif") if alt_folder else Path(f"cifs/{row_id}.cif")


def same_composition(formula_a: str, formula_b: str) -> bool:
    """
    Check reduced-composition equality using pymatgen Composition.

    What: Returns True if two formula strings represent the same reduced composition.
    Why: Avoid brittle string-equality on pretty formulas which may reorder elements.
    """
    if Composition is None:  # pragma: no cover
        return str(formula_a).strip() == str(formula_b).strip()
    try:
        ca = Composition(str(formula_a)).reduced_composition
        cb = Composition(str(formula_b)).reduced_composition
        return ca.almost_equals(cb)
    except Exception:
        return False


def crystal_system_from_number(n: Optional[int]) -> Optional[str]:
    if n is None:
        return None
    try:
        n = int(n)
    except Exception:
        return None
    if 1 <= n <= 2:
        return "triclinic"
    if 3 <= n <= 15:
        return "monoclinic"
    if 16 <= n <= 74:
        return "orthorhombic"
    if 75 <= n <= 142:
        return "tetragonal"
    if 143 <= n <= 167:
        return "trigonal"
    if 168 <= n <= 194:
        return "hexagonal"
    if 195 <= n <= 230:
        return "cubic"
    return None


def normalize_crystal_system(value: Any) -> Optional[str]:
    """
    Normalize a crystal system value (enum/string/None) to a lowercase string.

    Handles emmet CrystalSystem enums by using `.value` or `.name`.
    Returns one of: triclinic, monoclinic, orthorhombic, tetragonal, trigonal,
    hexagonal, cubic; or None when unknown.
    """
    if value is None:
        return None
    try:
        # Enum-like objects
        if hasattr(value, "value"):
            value = getattr(value, "value")
        elif hasattr(value, "name"):
            value = getattr(value, "name")
    except Exception:
        pass
    s = str(value).strip().lower()
    s = s.replace("_", "").replace("-", "")
    mapping = {
        "triclinic": "triclinic",
        "monoclinic": "monoclinic",
        "orthorhombic": "orthorhombic",
        "tetragonal": "tetragonal",
        "trigonal": "trigonal",
        "hexagonal": "hexagonal",
        "cubic": "cubic",
    }
    return mapping.get(s, None)


def infer_symmetry_from_structure(struct: Optional[Structure]) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Infer space group number, symbol, and crystal system from a structure.

    Returns (number, symbol, crystal_system) with all values optional if unavailable.
    """
    if struct is None or SpacegroupAnalyzer is None:
        return None, None, None
    try:
        sga = SpacegroupAnalyzer(struct, symprec=1e-2, angle_tolerance=5.0)
        num = sga.get_space_group_number()
        sym = sga.get_space_group_symbol()
        # Map number to system
        system = crystal_system_from_number(num)
        return num, sym, system
    except Exception:
        return None, None, None


# -------- Filters -------- #


def filter_icsd(
    icsd_id: Optional[int],
    api: MaterialsProjectAPI,
    include_deprecated_initial: bool = False,
    include_deprecated_retry: bool = True,
) -> List[MatchCandidate]:
    """
    Try ICSD-based lookup.

    What: Query MP by ICSD; optionally retry including deprecated docs.
    Why: Direct linkage is the highest-confidence signal when available.
    """
    if icsd_id is None:
        return []

    # First pass: without deprecated
    mpids = api.by_icsd(icsd_id, include_deprecated=include_deprecated_initial)
    if mpids:
        return [MatchCandidate(m, "icsd_match", 100, {"deprecated": False}) for m in mpids]

    # Optional retry: include deprecated
    if include_deprecated_retry:
        # Use None to include both deprecated and current
        mpids = api.by_icsd(icsd_id, include_deprecated=None)  # type: ignore[arg-type]
        return [MatchCandidate(m, "icsd_match", 100, {"deprecated": True}) for m in mpids]

    return []


def filter_doi(
    doi: Optional[str],
    api: MaterialsProjectAPI,
    *,
    include_deprecated_initial: bool = False,
    include_deprecated_retry: bool = True,
) -> List[MatchCandidate]:
    """
    Try DOI-based lookup.

    What: Query MP by DOI; optionally retry including deprecated docs.
    Why: Captures bibliographic matches when ICSD identifiers are missing.
    """
    doi_normalized = normalize_doi(doi)
    if not doi_normalized:
        return []

    results: List[MatchCandidate] = []
    seen: Set[str] = set()

    def _collect(docs: Iterable[MPDocumentSummary]) -> None:
        for doc in docs:
            mpid = getattr(doc, "material_id", None)
            if not mpid or mpid in seen:
                continue
            seen.add(mpid)
            notes: Dict[str, Any] = {
                "deprecated": getattr(doc, "deprecated", None),
                "matched_doi": doi_normalized,
            }
            mp_dois = getattr(doc, "dois", None)
            if mp_dois:
                notes["mp_dois"] = mp_dois
            formula_pretty = getattr(doc, "formula_pretty", None)
            if formula_pretty:
                notes["formula_pretty"] = formula_pretty
            results.append(MatchCandidate(mpid, "doi_match", 100, notes))

    docs = api.by_doi(doi_normalized, include_deprecated=include_deprecated_initial)
    _collect(docs)
    if results:
        return results

    if include_deprecated_retry:
        docs_retry = api.by_doi(doi_normalized, include_deprecated=None)
        _collect(docs_retry)

    return results


def filter_formula_sg(
    formula: str,
    spg_number: Optional[Any],
    spg_symbol: Optional[Any],
    api: MaterialsProjectAPI,
    include_deprecated: bool = False,
    allow_same_system: bool = True,
    use_structure_sg: bool = False,
) -> List[MatchCandidate]:
    """
    Filter by formula and space group (exact), with optional same-system fallback.

    What: Searches by formula and selects candidates with matching space group
    number or normalized symbol. If `allow_same_system` is True, also includes
    candidates in the same crystal system (e.g., P1 vs P-1 are both triclinic)
    but scores them lower.
    """
    summaries = api.by_formula(formula, include_deprecated=include_deprecated)

    # Optionally enrich symmetry from structures for better accuracy
    if use_structure_sg:
        mpids = [s.material_id for s in summaries]
        structs = api.structures_for(mpids)
        enriched = []
        for s in summaries:
            num, sym, system = infer_symmetry_from_structure(structs.get(s.material_id))
            if num is not None:
                s.spacegroup_number = num  # type: ignore[attr-defined]
            if sym is not None:
                s.spacegroup_symbol = sym  # type: ignore[attr-defined]
            if system is not None:
                s.crystal_system = system  # type: ignore[attr-defined]
            enriched.append(s)
        summaries = enriched

    ds_numbers = _coerce_int_list(spg_number)
    ds_symbols = _normalize_symbol_list(spg_symbol)
    numbers_set = set(ds_numbers)
    symbols_set = set(ds_symbols)

    ds_systems: Set[str] = set()
    for n in ds_numbers:
        sys = normalize_crystal_system(crystal_system_from_number(n))
        if sys:
            ds_systems.add(sys)
    if not ds_systems:
        for sym in ds_symbols:
            if sym in {"p1", "p-1"}:
                ds_systems.add("triclinic")

    exact: List[MatchCandidate] = []
    same_sys: List[MatchCandidate] = []
    seen: set[str] = set()
    for s in summaries:
        if not s.material_id or s.material_id in seen:
            continue
        seen.add(s.material_id)
        cand_num = _coerce_int_or_none(getattr(s, "spacegroup_number", None))
        cand_sym = normalize_spacegroup_symbol(getattr(s, "spacegroup_symbol", None))

        exact_match = (
            (cand_num is not None and cand_num in numbers_set)
            or (cand_sym is not None and cand_sym in symbols_set)
        )

        if exact_match:
            exact.append(
                MatchCandidate(
                    s.material_id,
                    "formula+sg",
                    70 - (5 if getattr(s, "deprecated", False) else 0),
                    {
                        "deprecated": getattr(s, "deprecated", None),
                        "spg_number": s.spacegroup_number,
                        "spg_symbol": s.spacegroup_symbol,
                        "crystal_system": normalize_crystal_system(getattr(s, "crystal_system", None)),
                    },
                )
            )
            continue

        if allow_same_system and ds_systems:
            cs_raw = getattr(s, "crystal_system", None)
            if cs_raw is None and s.spacegroup_number is not None:
                cs_raw = crystal_system_from_number(s.spacegroup_number)
            cs = normalize_crystal_system(cs_raw)
            if cs is not None and cs in ds_systems:
                same_sys.append(
                    MatchCandidate(
                        s.material_id,
                        "formula+sg_system",
                        60 - (5 if getattr(s, "deprecated", False) else 0),
                        {
                            "deprecated": getattr(s, "deprecated", None),
                            "spg_number": s.spacegroup_number,
                            "spg_symbol": s.spacegroup_symbol,
                            "crystal_system": cs,
                        },
                    )
                )

    return exact + same_sys


def filter_cif_match(
    formula: str,
    cif_path: Path,
    api: MaterialsProjectAPI,
    include_deprecated_candidates: bool = True,
    matcher_loose: bool = False,
    *,
    tier: Optional[str] = None,
    sweep: bool = False,
) -> List[MatchCandidate]:
    """
    Match CIF structure against MP structures of same formula.

    What: Loads the CIF, gathers candidate MP structures by formula, and checks
    geometric equivalence via StructureMatcher.
    Why: Provides high-confidence matches when symmetry/ICSD are unreliable.
    """
    if Structure is None or StructureMatcher is None:  # pragma: no cover
        return []
    if not cif_path.exists():
        return []

    try:
        target = Structure.from_file(str(cif_path))
    except Exception:
        return []

    # Candidate MP materials by formula
    summaries = api.by_formula(formula, include_deprecated=include_deprecated_candidates)
    if not summaries:
        # Fallback to chemsys search, then filter to same reduced composition
        try:
            from pymatgen.core import Composition  # type: ignore
            elems = sorted({el.symbol for el in Composition(formula)})
        except Exception:
            elems = []
        if elems:
            summaries = api.by_chemsys(elems, include_deprecated=include_deprecated_candidates)
            summaries = [
                s for s in summaries if s.formula_pretty and same_composition(s.formula_pretty, formula)
            ]
    mpids = [s.material_id for s in summaries]
    structures = api.structures_for(mpids)
    mp_summary_map = {s.material_id: s for s in summaries}

    # Determine tiers to try
    tiers_to_try: List[str]
    if sweep:
        tiers_to_try = CIF_MATCH_TIERS
    else:
        chosen = tier or ("loose" if matcher_loose else "strict")
        if chosen not in CIF_TIER_PARAMS:
            chosen = "strict"
        tiers_to_try = [chosen]

    # Try tiers in order; return matches from the first tier that yields any
    for t in tiers_to_try:
        params = CIF_TIER_PARAMS[t]
        try:
            matcher = StructureMatcher(
                ltol=params["ltol"],
                stol=params["stol"],
                angle_tol=params["angle_tol"],
                primitive_cell=params["primitive_cell"],
                attempt_supercell=params["attempt_supercell"],
                allow_subset=params["allow_subset"],
            )
        except Exception:
            matcher = StructureMatcher()

        tier_results: List[MatchCandidate] = []
        for mpid, s in structures.items():
            try:
                if matcher.fit(s, target):
                    tier_results.append(
                        MatchCandidate(
                            mpid,
                            "cif_match",
                            CIF_TIER_SCORES.get(t, 80) - (5 if getattr(mp_summary_map.get(mpid), "deprecated", False) else 0),
                            {
                                "deprecated": getattr(mp_summary_map.get(mpid), "deprecated", None),
                                "source": str(cif_path),
                                "tier": t,
                                "params": params,
                            },
                        )
                    )
            except Exception:
                continue
        if tier_results:
            return tier_results

    return []


def filter_formula_only(
    formula: str,
    api: MaterialsProjectAPI,
    include_deprecated: bool = True,
    spg_number: Optional[Any] = None,
    spg_symbol: Optional[Any] = None,
    use_structure_sg: bool = False,
) -> List[MatchCandidate]:
    """
    Fallback: formula-only candidates.

    What: Returns all candidates with the same reduced formula.
    Why: Last resort to maximize recall for manual triage or further narrowing.
    """
    summaries = api.by_formula(formula, include_deprecated=include_deprecated)
    if not summaries:
        # Fallback to chemsys search, then keep only same reduced composition
        try:
            from pymatgen.core import Composition  # type: ignore
            elems = sorted({el.symbol for el in Composition(formula)})
        except Exception:
            elems = []
        if elems:
            summaries = api.by_chemsys(elems, include_deprecated=include_deprecated)
            summaries = [
                s for s in summaries if s.formula_pretty and same_composition(s.formula_pretty, formula)
            ]
    # Optionally enrich with structure-derived symmetry to improve SG scoring
    if use_structure_sg:
        mpids = [s.material_id for s in summaries]
        structs = api.structures_for(mpids)
        enriched = []
        for s in summaries:
            num, sym, system = infer_symmetry_from_structure(structs.get(s.material_id))
            if num is not None:
                s.spacegroup_number = num  # type: ignore[attr-defined]
            if sym is not None:
                s.spacegroup_symbol = sym  # type: ignore[attr-defined]
            if system is not None:
                s.crystal_system = system  # type: ignore[attr-defined]
            enriched.append(s)
        summaries = enriched

    results: List[MatchCandidate] = []
    ds_numbers = _coerce_int_list(spg_number)
    ds_symbols = _normalize_symbol_list(spg_symbol)
    numbers_set = set(ds_numbers)
    symbols_set = set(ds_symbols)

    ds_systems: Set[str] = set()
    for n in ds_numbers:
        sys = normalize_crystal_system(crystal_system_from_number(n))
        if sys:
            ds_systems.add(sys)
    if not ds_systems:
        for sym in ds_symbols:
            if sym in {"p1", "p-1"}:
                ds_systems.add("triclinic")

    for s in summaries:
        # Classify SG relation for scoring
        relation = "unknown"
        score = 40
        # Always compute candidate crystal system for notes and comparison
        cs = getattr(s, "crystal_system", None) or crystal_system_from_number(s.spacegroup_number)
        cs = normalize_crystal_system(cs)
        cand_num = _coerce_int_or_none(getattr(s, "spacegroup_number", None))
        cand_sym = normalize_spacegroup_symbol(getattr(s, "spacegroup_symbol", None))

        if cand_num is not None and cand_num in numbers_set:
            relation = "exact"
            score = 65
        elif cand_sym is not None and cand_sym in symbols_set:
            relation = "exact"
            score = 63
        else:
            if ds_systems and cs in ds_systems:
                relation = "same_system"
                score = 55
            else:
                relation = "mismatch"
                score = 40
        if getattr(s, "deprecated", False):
            score -= 5
        results.append(
            MatchCandidate(
                s.material_id,
                "formula_only",
                score,
                {
                    "deprecated": getattr(s, "deprecated", None),
                    "spg_number": s.spacegroup_number,
                    "spg_symbol": s.spacegroup_symbol,
                    "crystal_system": cs,
                    "sg_relation": relation,
                },
            )
        )
    return results


# -------- Orchestration -------- #


def match_row(
    row: Mapping[str, Any],
    split: str,
    api: MaterialsProjectAPI,
    *,
    row_id_field: str = "id",
    include_deprecated_fallback: bool = True,
    cif_dir_map: Optional[Mapping[str, Path]] = None,
    base_dir: Optional[Path] = None,
) -> MatchResult:
    """
    Apply the matching pipeline to a single CSV row.

    What: Runs filters in priority order: ICSD → DOI → formula+SG → CIF → formula-only.
    Why: Encapsulates the end-to-end logic with clear I/O for integration.
    """
    candidates: List[MatchCandidate] = []

    # 1) Normalize CSV fields
    icsd_id = _coerce_int_or_none(row.get("ICSD ID"))
    formula_in = row.get("Reduced Composition", "")
    formula = normalize_formula(formula_in)
    doi_value = extract_row_doi(row)

    spg_number = _coerce_int_or_none(row.get("Space group #"))
    spg_symbol = normalize_spacegroup_symbol(row.get("Space group"))

    # 2) ICSD match
    candidates += filter_icsd(
        icsd_id=icsd_id,
        api=api,
        include_deprecated_initial=False,
        include_deprecated_retry=True,
    )
    if candidates:
        return MatchResult(best_mpid=candidates[0].mpid, candidates=candidates)

    # 3) DOI match
    candidates += filter_doi(
        doi=doi_value,
        api=api,
        include_deprecated_initial=False,
        include_deprecated_retry=True,
    )
    if candidates:
        return MatchResult(best_mpid=candidates[0].mpid, candidates=candidates)

    # 4) Formula + space group
    if spg_number is not None or spg_symbol is not None:
        candidates += filter_formula_sg(
            formula=formula,
            spg_number=spg_number,
            spg_symbol=spg_symbol,
            api=api,
            include_deprecated=include_deprecated_fallback,
        )
        if candidates:
            # Rank already ordered by insertion; return best first
            return MatchResult(best_mpid=candidates[0].mpid, candidates=candidates)

    # 5) CIF structure match
    row_id = row.get(row_id_field)
    if row_id:
        cif_path = resolve_cif_path(str(row_id), split=split, base_dir=base_dir, cif_dir_map=cif_dir_map)
        cif_matches = filter_cif_match(
            formula=formula,
            cif_path=cif_path,
            api=api,
            include_deprecated_candidates=include_deprecated_fallback,
        )
        if cif_matches:
            candidates += cif_matches
            return MatchResult(best_mpid=candidates[0].mpid, candidates=candidates)

    # 6) Formula-only fallback
    candidates += filter_formula_only(
        formula=formula,
        api=api,
        include_deprecated=include_deprecated_fallback,
    )
    best = candidates[0].mpid if candidates else None
    return MatchResult(best_mpid=best, candidates=candidates)
