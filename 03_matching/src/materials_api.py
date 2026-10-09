from __future__ import annotations

"""
Materials Project API wrapper used by the matching pipeline.

What: Provides small, clear methods to search MP by ICSD, formula/space group,
and to fetch structures by material_id.

Why: Keep external service access isolated and swappable, with consistent error
handling and minimal surface area. This makes the matching code easy to read,
test, and extend without scattering MP-specific details everywhere.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Optional


try:  # Optional import; methods will guard if unavailable.
    from mp_api.client import MPRester  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    MPRester = None  # type: ignore

try:
    from pymatgen.core.structure import Structure  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    Structure = object  # type: ignore


@dataclass
class MPDocumentSummary:
    """Lightweight projection of MP summary fields we care about."""

    material_id: str
    formula_pretty: Optional[str] = None
    spacegroup_symbol: Optional[str] = None
    spacegroup_number: Optional[int] = None
    crystal_system: Optional[str] = None
    deprecated: Optional[bool] = None
    dois: Optional[List[str]] = None


def normalize_doi_value(value: Any) -> Optional[str]:
    """Best-effort normalization of DOI strings."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    lower = s.lower()
    if lower.startswith("doi:"):
        s = s[4:]
        lower = s.lower()
    if "doi.org/" in lower:
        idx = lower.index("doi.org/") + len("doi.org/")
        s = s[idx:]
        lower = s.lower()
    # Capture canonical DOI substring
    match = re.search(r"10\.\d{4,9}/\S+", s, re.IGNORECASE)
    if match:
        return match.group(0).rstrip(".").lower()
    if lower.startswith("10."):
        return lower.rstrip(".")
    return None


class MaterialsProjectAPI:
    """
    Thin wrapper around mp_api.MPRester for the subset of queries we need.

    Notes:
    - All methods avoid over-constraining server filters except for stable keys
      (formula, material_ids, deprecated). For fields like space group, we fetch
      summaries then filter client-side to avoid brittle query syntax.
    - When mp_api is not installed or API calls fail, methods return empty lists
      and include informative error messages via exceptions where appropriate.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key

    def _get_client(self):
        if MPRester is None:  # pragma: no cover - environment-dependent
            raise ImportError(
                "mp_api is not installed. Install mp-api and set an API key."
            )
        return MPRester(self._api_key) if self._api_key else MPRester()

    def _summary_route(self, mpr):
        """Return a summary route compatible with both old and new mp-api.

        Prefers `mpr.materials.summary` (new) and falls back to `mpr.summary` (old),
        avoiding deprecation warnings where possible.
        """
        try:
            materials = getattr(mpr, "materials", None)
            if materials is not None and getattr(materials, "summary", None) is not None:
                return materials.summary
        except Exception:
            pass
        return mpr.summary

    def _extract_symmetry(self, doc: Any) -> Dict[str, Optional[Any]]:
        """Best-effort extraction of symmetry fields from a SummaryDoc.

        Handles both attribute-style (pydantic model) and mapping-style access.
        Returns a dict with keys: symbol, number, crystal_system.
        """
        out: Dict[str, Optional[Any]] = {
            "symbol": None,
            "number": None,
            "crystal_system": None,
        }
        try:
            sym = getattr(doc, "symmetry", None)
            if sym is None:
                sym = getattr(doc, "symmetry_data", None)
            # Mapping-like access
            if isinstance(sym, dict):
                spg = sym.get("space_group") or sym.get("spacegroup") or {}
                out["symbol"] = spg.get("symbol") or spg.get("symbol_refined") or spg.get("name")
                out["number"] = spg.get("number")
                out["crystal_system"] = sym.get("crystal_system") or sym.get("crystalSystem")
                return out
            # Attribute-like access
            if sym is not None:
                # crystal system
                try:
                    out["crystal_system"] = getattr(sym, "crystal_system", None) or getattr(sym, "crystalSystem", None)
                except Exception:
                    pass
                # space group sub-object
                spg = None
                try:
                    spg = getattr(sym, "space_group", None) or getattr(sym, "spacegroup", None)
                except Exception:
                    spg = None
                if isinstance(spg, dict):
                    out["symbol"] = spg.get("symbol") or spg.get("symbol_refined") or spg.get("name")
                    out["number"] = spg.get("number")
                    return out
                if spg is not None:
                    try:
                        out["symbol"] = getattr(spg, "symbol", None) or getattr(spg, "symbol_refined", None) or getattr(spg, "name", None)
                    except Exception:
                        pass
                    try:
                        out["number"] = getattr(spg, "number", None)
                    except Exception:
                        pass
        except Exception:
            pass
        return out

    def _extract_dois(self, doc: Any) -> List[str]:
        """Collect DOI identifiers exposed on a SummaryDoc."""

        dois: set[str] = set()
        try:
            raw_doi = getattr(doc, "doi", None)
            if raw_doi:
                if isinstance(raw_doi, (list, tuple, set)):
                    for item in raw_doi:
                        norm = normalize_doi_value(item)
                        if norm:
                            dois.add(norm)
                else:
                    norm = normalize_doi_value(raw_doi)
                    if norm:
                        dois.add(norm)
        except Exception:
            pass

        try:
            refs = getattr(doc, "references", None)
            if isinstance(refs, dict):
                # mp-api may expose {"doi": [...]} or nested entries
                for v in refs.values():
                    if isinstance(v, (list, tuple, set)):
                        for item in v:
                            norm = normalize_doi_value(item)
                            if norm:
                                dois.add(norm)
                    else:
                        norm = normalize_doi_value(v)
                        if norm:
                            dois.add(norm)
            elif isinstance(refs, (list, tuple, set)):
                for ref in refs:
                    try:
                        if isinstance(ref, dict):
                            norm = normalize_doi_value(ref.get("doi") or ref.get("DOI"))
                            if norm:
                                dois.add(norm)
                            # Occasionally DOI embedded in "reference" text
                            norm = normalize_doi_value(ref.get("reference") or ref.get("citation"))
                            if norm:
                                dois.add(norm)
                        else:
                            norm = normalize_doi_value(getattr(ref, "doi", None))
                            if norm:
                                dois.add(norm)
                            norm = normalize_doi_value(getattr(ref, "reference", None))
                            if norm:
                                dois.add(norm)
                    except Exception:
                        continue
        except Exception:
            pass

        return sorted(dois)

    # -------- Query helpers -------- #
    def by_icsd(self, icsd_id: int, include_deprecated: Optional[bool] = False) -> List[str]:
        """
        Find MP material_ids linked to a given ICSD ID.

        What: Searches MP summary collection and returns candidate material_ids.
        Why: Direct ICSD linkage is the most reliable match when present.

        Implementation note: MP exposes external database IDs in summary docs,
        but direct server-side filtering by ICSD can vary by mp_api version.
        For stability, we search broadly by deprecated flag and then filter
        client-side by database IDs when present.
        """
        try:
            with self._get_client() as mpr:
                summary = self._summary_route(mpr)
                # deprecated param semantics:
                # - None => do not filter (include both current and deprecated)
                # - False => only current
                # - True => only deprecated (rarely desired)
                dep_param = include_deprecated if include_deprecated is not True else True
                docs = summary.search(
                    deprecated=dep_param,
                    fields=[
                        "material_id",
                        "formula_pretty",
                        "database_IDs",
                    ],
                )
        except Exception:
            return []

        mpids: List[str] = []
        for d in docs:
            # Known variants across MP versions: `database_IDs` may hold `icsd`.
            try:
                db_ids = getattr(d, "database_IDs", None) or {}
                icsd_list = db_ids.get("icsd") or db_ids.get("ICSD") or []
                if isinstance(icsd_list, (list, tuple)) and int(icsd_id) in {
                    int(x) for x in icsd_list if x is not None
                }:
                    mpids.append(d.material_id)
            except Exception:
                # Best-effort filtering; ignore malformed docs.
                continue
        return mpids

    def by_formula(self, formula: str, include_deprecated: bool = False) -> List[MPDocumentSummary]:
        """
        Search by (reduced) formula and project to stable summary fields.

        What: Retrieves a list of candidate materials for a formula.
        Why: Forms the base candidate set for more selective filters like
        space group and CIF structure matching.
        """
        def _search(include_refs: bool) -> List[Any]:
            fields = [
                "material_id",
                "formula_pretty",
                "symmetry",
                "deprecated",
            ]
            if include_refs:
                fields += ["references", "doi"]
            with self._get_client() as mpr:
                summary = self._summary_route(mpr)
                dep_param: Optional[bool] = None if include_deprecated else False
                return summary.search(
                    formula=[formula],
                    deprecated=dep_param,
                    fields=fields,
                )

        try:
            docs = _search(include_refs=True)
        except Exception:
            try:
                docs = _search(include_refs=False)
            except Exception:
                return []

        results: List[MPDocumentSummary] = []
        for d in docs:
            sym = self._extract_symmetry(d)
            spg_sym = sym.get("symbol")
            spg_no: Optional[int] = sym.get("number")  # type: ignore[assignment]
            crystal: Optional[str] = sym.get("crystal_system")  # type: ignore[assignment]
            results.append(
                MPDocumentSummary(
                    material_id=d.material_id,
                    formula_pretty=getattr(d, "formula_pretty", None),
                    spacegroup_symbol=spg_sym,
                    spacegroup_number=spg_no,
                    crystal_system=crystal,
                    deprecated=getattr(d, "deprecated", None),
                    dois=self._extract_dois(d),
                )
            )
        return results

    def by_doi(self, doi: str, include_deprecated: Optional[bool] = False) -> List[MPDocumentSummary]:
        """
        Search materials that cite a specific DOI.

        What: Retrieves candidate materials whose references include the DOI.
        Why: Enables direct bibliographic linkage when ICSD identifiers are absent.
        """
        normalized = normalize_doi_value(doi)
        if not normalized:
            return []

        dep_param: Optional[bool]
        if include_deprecated in (True, False):
            dep_param = include_deprecated
        else:
            dep_param = None

        try:
            with self._get_client() as mpr:
                summary = self._summary_route(mpr)
                docs: List[Any] = []
                search_kwargs_list = [
                    {"references": [normalized]},
                    {"doi": [normalized]},
                    {"doi": normalized},
                ]
                for kwargs in search_kwargs_list:
                    try:
                        docs = summary.search(
                            deprecated=dep_param,
                            fields=[
                                "material_id",
                                "formula_pretty",
                                "symmetry",
                                "deprecated",
                                "references",
                                "doi",
                            ],
                            **kwargs,
                        )
                    except Exception:
                        docs = []
                    if docs:
                        break
        except Exception:
            return []

        results: List[MPDocumentSummary] = []
        for d in docs:
            sym = self._extract_symmetry(d)
            spg_sym = sym.get("symbol")
            spg_no: Optional[int] = sym.get("number")  # type: ignore[assignment]
            crystal: Optional[str] = sym.get("crystal_system")  # type: ignore[assignment]
            results.append(
                MPDocumentSummary(
                    material_id=d.material_id,
                    formula_pretty=getattr(d, "formula_pretty", None),
                    spacegroup_symbol=spg_sym,
                    spacegroup_number=spg_no,
                    crystal_system=crystal,
                    deprecated=getattr(d, "deprecated", None),
                    dois=self._extract_dois(d),
                )
            )
        return results

    def by_chemsys(self, elements: Iterable[str], include_deprecated: bool = False) -> List[MPDocumentSummary]:
        """
        Search by chemical system (dash-joined sorted elements, e.g., "Li-O-Bi").

        What: Broader search to retrieve all compositions within an element set.
        Why: Serves as a fallback when direct formula queries are sparse.
        """
        elems = sorted({str(e) for e in elements if e})
        if not elems:
            return []
        chemsys = "-".join(elems)
        def _search(include_refs: bool) -> List[Any]:
            fields = [
                "material_id",
                "formula_pretty",
                "symmetry",
                "deprecated",
            ]
            if include_refs:
                fields += ["references", "doi"]
            with self._get_client() as mpr:
                summary = self._summary_route(mpr)
                dep_param: Optional[bool] = None if include_deprecated else False
                return summary.search(
                    chemsys=[chemsys],
                    deprecated=dep_param,
                    fields=fields,
                )

        try:
            docs = _search(include_refs=True)
        except Exception:
            try:
                docs = _search(include_refs=False)
            except Exception:
                return []

        results: List[MPDocumentSummary] = []
        for d in docs:
            sym = self._extract_symmetry(d)
            spg_sym = sym.get("symbol")
            spg_no: Optional[int] = sym.get("number")  # type: ignore[assignment]
            crystal: Optional[str] = sym.get("crystal_system")  # type: ignore[assignment]
            results.append(
                MPDocumentSummary(
                    material_id=d.material_id,
                    formula_pretty=getattr(d, "formula_pretty", None),
                    spacegroup_symbol=spg_sym,
                    spacegroup_number=spg_no,
                    crystal_system=crystal,
                    deprecated=getattr(d, "deprecated", None),
                    dois=self._extract_dois(d),
                )
            )
        return results

    def by_formula_sg(
        self,
        formula: str,
        spg_number: Optional[int] = None,
        spg_symbol: Optional[str] = None,
        include_deprecated: bool = False,
    ) -> List[str]:
        """
        Filter candidates by formula and (optionally) space group attributes.

        What: Returns material_ids whose formula matches and whose space group
        matches the provided number or normalized symbol.
        Why: Provides a precise but still broad query when ICSD is absent.
        """
        candidates = self.by_formula(formula, include_deprecated=include_deprecated)

        def _norm_symbol(s: Optional[str]) -> Optional[str]:
            if not s:
                return None
            s = s.replace(" ", "")
            s = s.replace("−", "-")  # normalize minus
            s = s.replace("_", "-")
            return s

        norm_target_sym = _norm_symbol(spg_symbol)

        filtered: List[str] = []
        for c in candidates:
            if spg_number is not None and c.spacegroup_number == spg_number:
                filtered.append(c.material_id)
                continue
            if norm_target_sym is not None and _norm_symbol(c.spacegroup_symbol) == norm_target_sym:
                filtered.append(c.material_id)
                continue
            if spg_number is None and norm_target_sym is None:
                filtered.append(c.material_id)

        return filtered

    def structures_for(self, mpids: Iterable[str]) -> Dict[str, Structure]:
        """
        Fetch crystal structures for given material_ids.

        What: Returns a dict of material_id -> pymatgen Structure.
        Why: Enables geometric matching against CIFs via StructureMatcher.
        """
        ids = list(dict.fromkeys(mpids))  # de-duplicate, preserve order
        if not ids:
            return {}
        try:
            with self._get_client() as mpr:
                summary = self._summary_route(mpr)
                docs = summary.search(
                    material_ids=ids,
                    fields=["material_id", "structure"],
                )
        except Exception:
            return {}

        out: Dict[str, Structure] = {}
        for d in docs:
            try:
                s = getattr(d, "structure", None)
                if s is not None:
                    out[d.material_id] = s
            except Exception:
                continue
        return out
