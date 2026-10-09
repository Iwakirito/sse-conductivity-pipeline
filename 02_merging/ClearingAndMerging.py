from pathlib import Path

import pandas as pd

# Directory containing the CSV files; keeps paths relative to this script.
csv_dir = Path(__file__).resolve().parent

# Helper to load a CSV into a pandas DataFrame; tries UTF-8 then falls back.
def load_csv(filename: str, *, encodings=("utf-8", "latin-1", "cp1252")) -> pd.DataFrame:
    csv_path = csv_dir / filename
    last_error = None
    for encoding in encodings:
        try:
            return pd.read_csv(csv_path, encoding=encoding)
        except UnicodeDecodeError as err:
            last_error = err
    raise last_error if last_error else FileNotFoundError(csv_path)

acsomega_df = load_csv("ACSOmegaSGReady.csv")
liverpool_df = load_csv("LiverpoolSGReady.csv")
obelix_df = load_csv("ObelixSGReady.csv")
