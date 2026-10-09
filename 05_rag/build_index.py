# build_index.py  — schema-agnostic CSV → FAISS index
import os, json, hashlib
import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

CSV_PATH = "data/MyDatabase.csv"  # change via CLI if you want
os.makedirs("artifacts", exist_ok=True)

# Load and normalize headers
df = pd.read_csv(CSV_PATH, dtype=str)  # keep strings
orig_cols = list(df.columns)
norm_cols = (
    pd.Index(orig_cols)
    .str.strip().str.replace(r"\s+", "_", regex=True)
    .str.replace(r"[^A-Za-z0-9_]", "", regex=True)
)
df.columns = norm_cols

# Choose an identifier column automatically
PRIORITY = [
    "id","mp_id","material_id","identifier","uid","doi","name","label"
]
id_col = next((c for c in PRIORITY if c in df.columns), None)
if id_col is None:
    id_col = df.columns[0]  # fallback
df["_rowid"] = np.arange(len(df))  # stable fallback

def safe(v: str) -> str:
    return "NA" if (v is None or v != v or v.strip() == "") else v.strip()

# Build a compact "card" per row by serializing ALL columns
cards = []
for i, row in df.iterrows():
    kv = []
    # First, a canonical ID line
    kv.append(f"ID: {safe(str(row.get(id_col, 'NA')))}")
    kv.append(f"ROW: {int(row['_rowid'])}")
    # Then all columns as key:value
    for col in df.columns:
        if col == "_rowid": 
            continue
        kv.append(f"{col}: {safe(str(row[col]))}")
    text = "; ".join(kv)
    # Optional: truncate super-long cards
    if len(text) > 4000:
        text = text[:4000] + " …"
    cards.append(text)

# Embed + index
model_name = "sentence-transformers/all-MiniLM-L6-v2"
emb_model = SentenceTransformer(model_name)
embs = emb_model.encode(cards, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
index = faiss.IndexFlatIP(embs.shape[1])
index.add(embs)

# Persist
faiss.write_index(index, "artifacts/faiss.index")
with open("artifacts/cards.jsonl", "w", encoding="utf-8") as f:
    for c in cards:
        f.write(json.dumps({"text": c}, ensure_ascii=False) + "\n")

meta = {
    "model": model_name,
    "n": len(cards),
    "id_col": id_col,
    "orig_cols": orig_cols,
    "norm_cols": list(df.columns),
    "csv_sha256": hashlib.sha256(open(CSV_PATH,"rb").read()).hexdigest(),
    "source_csv": os.path.basename(CSV_PATH),
}
with open("artifacts/meta.json", "w") as f:
    json.dump(meta, f, indent=2)

print(f"OK. Built {len(cards)} cards. ID column = {id_col}. Source = {meta['source_csv']}")
