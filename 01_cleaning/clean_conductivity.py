import argparse
import re
from typing import List, Tuple

import numpy as np
import pandas as pd

UNICODE_MAP = {
    "×": "*",
    "∙": "*",
    "·": "*",
    "−": "-",
    "–": "-",
    "—": "-",
    "∼": "~",
    "": "-",
}

ENCODING_ERROR_CHARS = {"â", "Ã", "�"}

PLAIN_FLOAT_RE = re.compile(r"^[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?$")
SCI_NOTATION_RE = re.compile(r"^[+-]?\d*\.?\d+\*10(?:\^([+-]?\d+)|([+-]?\d+))$")
POWER_OF_TEN_RE = re.compile(r"^10(?:\^([+-]?\d+)|([+-]?\d+))$")
POWER_OF_TEN_LEADING_DASH_RE = re.compile(r"^-10(?:\^([+-]?\d+)|([+-]?\d+))$")


def normalize_conductivity_string(raw: str) -> str:
    if raw is None:
        return ""
    text = str(raw)
    for old, new in UNICODE_MAP.items():
        text = text.replace(old, new)
    text = re.sub(r"(?i)x\s*10", "*10", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=\d)\s*\?\s*(?=\d)", "-", text)
    text = re.sub(r"\s*\*\s*", "*", text)
    text = re.sub(r"\s*\^\s*", "^", text)
    text = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "-", text)
    text = re.sub(r"-\s+(?=\d)", "-", text)
    return text


def _token_is_numeric(token: str) -> bool:
    try:
        evaluate_numeric_token(token)
        return True
    except ValueError:
        return False


def _split_range_dash(text: str) -> Tuple[str, str] | None:
    for idx, ch in enumerate(text):
        if ch != "-":
            continue
        left = text[:idx].strip()
        right = text[idx + 1 :].strip()
        if not left or not right:
            continue
        prev_segment = text[:idx]
        if prev_segment.endswith("10") or prev_segment.endswith("e") or prev_segment.endswith("E") or prev_segment.endswith("^"):
            continue
        if left and right:
            return left, right
    return None


def classify_conductivity(normalized: str) -> Tuple[str, List[str]]:
    if not normalized:
        return "unknown", []
    if any(char in normalized for char in ENCODING_ERROR_CHARS):
        return "encoding_error", []
    lower = normalized.lower()
    if lower.startswith("to "):
        upper = normalized[2:].strip()
        if upper and _token_is_numeric(upper):
            return "open_upper", [upper]
    if "±" in normalized:
        central = normalized.split("±", 1)[0].strip()
        if central and _token_is_numeric(central):
            return "plus_minus", [central]
    if "~" in normalized:
        parts = [part.strip() for part in normalized.split("~") if part.strip()]
        if len(parts) == 2 and all(_token_is_numeric(p) for p in parts):
            return "approx_range", parts
    if re.search(r"\bto\b", lower) and not lower.startswith("to "):
        parts = re.split(r"\bto\b", normalized, flags=re.IGNORECASE)
        if len(parts) == 2:
            left, right = parts[0].strip(), parts[1].strip()
            if left and right and all(_token_is_numeric(p) for p in (left, right)):
                return "range_to", [left, right]
    multi_sep = re.split(r"\s*(?:,|\band\b|\bor\b|;)\s*", normalized, flags=re.IGNORECASE)
    multi_values = [part for part in multi_sep if part]
    if len(multi_values) >= 2 and all(_token_is_numeric(val) for val in multi_values):
        return "multi_value", multi_values
    range_dash_parts = _split_range_dash(normalized)
    if range_dash_parts and all(_token_is_numeric(p) for p in range_dash_parts):
        return "range_dash", list(range_dash_parts)
    if POWER_OF_TEN_LEADING_DASH_RE.match(normalized):
        cleaned = normalized[1:]
        return "power_of_ten_leading_dash", [cleaned]
    if POWER_OF_TEN_RE.match(normalized):
        return "power_of_ten", [normalized]
    if SCI_NOTATION_RE.match(normalized):
        return "single_sci", [normalized]
    if PLAIN_FLOAT_RE.match(normalized):
        return "single_plain", [normalized]
    return "unknown", []


def evaluate_numeric_token(token: str) -> float:
    if token is None:
        raise ValueError("empty token")
    cleaned = str(token).strip()
    if not cleaned:
        raise ValueError("empty token")
    cleaned = re.sub(r"[\(\)\[\]]", "", cleaned)
    cleaned = re.sub(r"[A-Za-z/%]+$", "", cleaned).strip()
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        raise ValueError("empty token")
    if PLAIN_FLOAT_RE.match(cleaned):
        return float(cleaned)
    sci_match = SCI_NOTATION_RE.match(cleaned)
    if sci_match:
        coeff = float(cleaned.split("*10")[0])
        exponent = int(sci_match.group(1) or sci_match.group(2))
        return coeff * (10 ** exponent)
    power_match = POWER_OF_TEN_LEADING_DASH_RE.match(cleaned) or POWER_OF_TEN_RE.match(cleaned)
    if power_match:
        exponent = int(power_match.group(1) or power_match.group(2))
        sign = -1 if cleaned.startswith("-") else 1
        return sign * (10 ** exponent)
    raise ValueError(f"unsupported numeric token: {token}")


def _geometric_mean(values: List[float]) -> float:
    arr = np.array(values, dtype=float)
    if np.any(arr <= 0):
        raise ValueError("non-positive value in geometric mean")
    return float(10 ** np.mean(np.log10(arr)))


def _finalize_ok(value: float, pattern: str) -> Tuple[float, str, str]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan, pattern, "manual_review"
    if not np.isfinite(numeric) or numeric <= 0:
        return np.nan, pattern, "manual_review"
    return numeric, pattern, "ok"


def parse_conductivity(raw: str) -> Tuple[float, str, str]:
    normalized = normalize_conductivity_string(raw)
    pattern, parts = classify_conductivity(normalized)
    try:
        if pattern == "single_plain":
            value = evaluate_numeric_token(parts[0])
            return _finalize_ok(value, pattern)
        if pattern == "single_sci":
            value = evaluate_numeric_token(parts[0])
            return _finalize_ok(value, pattern)
        if pattern == "power_of_ten":
            value = evaluate_numeric_token(parts[0])
            return _finalize_ok(value, pattern)
        if pattern == "range_to":
            left, right = (evaluate_numeric_token(p) for p in parts)
            if left > 0 and right > 0:
                return _finalize_ok(_geometric_mean([left, right]), pattern)
            return np.nan, pattern, "manual_review"
        if pattern == "range_dash":
            return np.nan, pattern, "manual_review"
        if pattern == "open_upper":
            upper = evaluate_numeric_token(parts[0])
            return _finalize_ok(upper, pattern)
        if pattern == "multi_value":
            values = [evaluate_numeric_token(p) for p in parts]
            if all(v > 0 for v in values):
                return _finalize_ok(_geometric_mean(values), pattern)
            return np.nan, pattern, "manual_review"
        if pattern == "plus_minus":
            central = evaluate_numeric_token(parts[0])
            return _finalize_ok(central, pattern)
        if pattern == "approx_range":
            left, right = (evaluate_numeric_token(p) for p in parts)
            if left > 0 and right > 0:
                return _finalize_ok(_geometric_mean([left, right]), pattern)
            return np.nan, pattern, "manual_review"
        if pattern == "power_of_ten_leading_dash":
            adjusted = parts[0].lstrip("-")
            value = evaluate_numeric_token(adjusted)
            return _finalize_ok(value, pattern)
        if pattern in {"encoding_error", "unknown"}:
            return np.nan, pattern, "manual_review"
    except (ValueError, OverflowError):
        return np.nan, pattern, "manual_review"
    return np.nan, pattern, "manual_review"


def _load_csv(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def _print_manual_review(df: pd.DataFrame) -> None:
    if df.empty:
        print("No rows flagged for manual review.")
        return
    preview = df[["Ionic Conductivity", "conductivity_pattern"]].head(20).copy()
    for col in preview.select_dtypes(include="object"):
        preview[col] = preview[col].apply(
            lambda val: val.encode("ascii", "replace").decode("ascii") if isinstance(val, str) else val
        )
    print(preview.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean ionic conductivity data.")
    parser.add_argument(
        "--input",
        default="data/conductivity_data.csv",
        help="Path to the raw conductivity CSV file.",
    )
    parser.add_argument(
        "--output",
        default="conductivity_data_clean.csv",
        help="Path for the cleaned CSV output.",
    )
    args = parser.parse_args()

    df = _load_csv(args.input)
    if "Ionic Conductivity" not in df.columns:
        raise KeyError("Column 'Ionic Conductivity' not found in input data.")
    parsed = df["Ionic Conductivity"].apply(parse_conductivity)
    parsed_df = pd.DataFrame(parsed.tolist(), columns=["conductivity_clean", "conductivity_pattern", "conductivity_parse_status"])
    df = pd.concat([df, parsed_df], axis=1)
    df.to_csv(args.output, index=False)

    print("conductivity_pattern value counts:")
    print(df["conductivity_pattern"].value_counts(dropna=False))
    print("\nconductivity_parse_status value counts:")
    print(df["conductivity_parse_status"].value_counts(dropna=False))
    manual_review = df[df["conductivity_parse_status"] == "manual_review"]
    print("\nManual review sample (up to 20 rows):")
    _print_manual_review(manual_review)
    print(f"\nCleaned data saved to {args.output}")


if __name__ == "__main__":
    main()
