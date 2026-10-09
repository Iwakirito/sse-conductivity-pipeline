# app.py
import json
import re
from pathlib import Path
from typing import List, Tuple, Optional

import faiss
import numpy as np
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


# ---------------------------
# Config
# ---------------------------
ARTIFACT_DIR = Path("artifacts")
INDEX_PATH = ARTIFACT_DIR / "faiss.index"
CARDS_PATH = ARTIFACT_DIR / "cards.jsonl"
META_PATH = ARTIFACT_DIR / "meta.json"

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

OLLAMA_HOST = "http://127.0.0.1:11435"
OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"

DEFAULT_K = 12
DEFAULT_TOP_N = 5


# ---------------------------
# Load artifacts at startup
# ---------------------------
if not INDEX_PATH.exists() or not CARDS_PATH.exists():
    raise RuntimeError(
        "Artifacts missing. Run `python build_index.py` first.\n"
        f"Expected: {INDEX_PATH} and {CARDS_PATH}"
    )

index = faiss.read_index(str(INDEX_PATH))

cards: List[str] = []
with open(CARDS_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            cards.append(line)

meta = {}
if META_PATH.exists():
    meta = json.load(open(META_PATH, "r", encoding="utf-8"))

embedder = SentenceTransformer(EMBED_MODEL_NAME)


# ---------------------------
# Helpers
# ---------------------------
def normalize_vec(v: np.ndarray) -> np.ndarray:
    v = v.astype("float32")
    n = np.linalg.norm(v)
    if n == 0:
        return v
    return v / n


def embed_text(text: str) -> np.ndarray:
    v = embedder.encode([text], convert_to_numpy=True)[0]
    return normalize_vec(v)


def retrieve_cards(question: str, k: int) -> List[str]:
    qv = embed_text(question).reshape(1, -1)
    scores, idxs = index.search(qv, k)
    idxs = idxs[0].tolist()
    out = []
    for i in idxs:
        if 0 <= i < len(cards):
            out.append(cards[i])
    return out


def extract_field(card: str, field: str) -> Optional[str]:
    """
    Extracts a field from a card formatted like:
    "NewID: ACS-123; Conductivity_S__cm: 1.0E-4; ..."
    """
    m = re.search(rf"{re.escape(field)}:\s*([^;]+)", card)
    return m.group(1).strip() if m else None


def parse_float(x) -> Optional[float]:
    try:
        return float(str(x).replace("E", "e"))
    except Exception:
        return None


def top_n_from_cards(
    cards: List[str],
    n: int = DEFAULT_TOP_N,
    field: str = "Conductivity_S__cm",
    unique_field: str = "NewID"
) -> List[Tuple[str, float, str]]:
    """
    Deterministically selects top-n unique entries by `field`
    within the retrieved subset.
    Returns list of tuples: (unique_id, value, full_card)
    """
    rows: List[Tuple[str, float, str]] = []
    for c in cards:
        uid = extract_field(c, unique_field)
        val_str = extract_field(c, field)
        val = parse_float(val_str)
        if uid and val is not None:
            rows.append((uid, val, c))

    rows.sort(key=lambda t: t[1], reverse=True)

    seen = set()
    out = []
    for uid, val, c in rows:
        if uid in seen:
            continue
        seen.add(uid)
        out.append((uid, val, c))
        if len(out) == n:
            break
    return out


def call_ollama(prompt: str, timeout_s=600, retries=3) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0}
    }

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=timeout_s)
            if not r.ok:
                raise RuntimeError(f"Ollama error {r.status_code}: {r.text}")
            return r.json().get("response", "").strip()
        except Exception as e:
            last_err = e
            print(f"[call_ollama] attempt {attempt}/{retries} failed: {e}")
            time.sleep(2)

    raise HTTPException(status_code=500, detail=str(last_err))


def build_prompt(question: str, top_records: List[Tuple[str, float, str]]) -> str:
    """
    LLM only narrates Top Records selected by code.
    """
    top_context = "\n".join(
        [
            f"- NewID: {uid}; {extract_field(card,'ChemFormula')=}; "
            f"best_mpid: {extract_field(card,'best_mpid')}; "
            f"Conductivity_S__cm: {val:.3e}; "
            f"Temperature__C: {extract_field(card,'Temperature__C')}; "
            f"Tier: {extract_field(card,'Tier')}; "
            f"Family: {extract_field(card,'Family')}"
            for uid, val, card in top_records
        ]
    )

    return f"""
You are given Top Records selected deterministically from the database.
Answer ONLY using these Top Records. Do not invent IDs or values.

Question:
{question}

Top Records:
{top_context}

Instructions:
1) List the Top Records in order as bullets:
   NewID → Conductivity_S__cm (with units), ChemFormula, best_mpid, Temperature__C, Tier, Family.
2) Provide 2–3 concise scientific sentences interpreting the result.
3) If Temperature__C is missing (nan), say "not reported" instead of inventing.
"""


# ---------------------------
# FastAPI
# ---------------------------
app = FastAPI(title="SSE Conductivity RAG", version="1.0")


class AskReq(BaseModel):
    question: str
    k: int = DEFAULT_K
    top_n: int = DEFAULT_TOP_N


@app.post("/ask")
def ask(req: AskReq):
    retrieved = retrieve_cards(req.question, req.k)

    tops = top_n_from_cards(
        retrieved,
        n=req.top_n,
        field="Conductivity_S__cm",
        unique_field="NewID"
    )

    if len(tops) == 0:
        prompt = f"""
You retrieved no valid numeric records for ordering.
Answer ONLY using the retrieved subset.
If you cannot find relevant data, reply exactly:
"no data at specified conditions."

Question:
{req.question}

Retrieved Records:
""" + "\n".join([f"- {c}" for c in retrieved])
        ans = call_ollama(prompt)
        return {"answer": ans, "retrieved": retrieved, "top_records": []}

    prompt = build_prompt(req.question, tops)
    ans = call_ollama(prompt)

    top_records_out = [
        {
            "NewID": uid,
            "Conductivity_S__cm": val,
            "record": card
        }
        for uid, val, card in tops
    ]

    return {
        "answer": ans,
        "retrieved": retrieved,
        "top_records": top_records_out,
        "meta": {
            "k": req.k,
            "top_n": req.top_n,
            "embed_model": EMBED_MODEL_NAME,
            "ollama_model": OLLAMA_MODEL,
            "csv_sha256": meta.get("csv_sha256", None),
            "id_col": meta.get("id_col", None),
            "n_rows": meta.get("n", None)
        }
    }


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "SSE conductivity RAG service running. Use POST /ask or go to /docs."
    }
