# demo_examples.py
import json
import time
import requests
from pathlib import Path

API = "http://127.0.0.1:8000/ask"

# -------------------------
# Curated toy-demo questions (database-first, RAG as interface)
# -------------------------

# -------------------------
# Curated toy-demo questions (only Q2 needs rerun)
# -------------------------

# -------------------------
# Final "one last try" questions
# Focus: polish family landscape + highlight LLZO/MP linkage
# -------------------------

QUESTIONS = [

    {
        "tag": "Q_LLZO_spread_mp942733",
        "body": {
            "question":
                "Consider the garnet-type solid electrolyte Li7La3Zr2O12 (often abbreviated LLZO). "
                "Using this dataset, identify entries that clearly correspond to LLZO. "
                "In practice, look for records where the ChemFormula is close to Li7La3Zr2O12 "
                "(small deviations in stoichiometry are acceptable) and/or where the combination "
                "of Family = 'Garnet' and best_mpid corresponds to Li7La3Zr2O12 (for example, mp-942733). "
                "List up to 15 such entries. For each entry, report: NewID, ChemFormula, best_mpid, "
                "Conductivity_S__cm, Temperature__C, Tier, and Family. "
                "Then summarize in a few sentences the range of reported conductivities and "
                "Tiers for LLZO in this dataset, and comment on how having all these measurements "
                "mapped onto a single Materials Project structure helps interpret this spread.",
            "k": 80,
            "top_n": 30
        }
    },

    # Q2: High-conductivity landscape by Family in the high-confidence subset (T1/T2)
    # Goal: get a family-level view that you can cross-check against the literature,
    # without dragging in the weird T4 / Unassigned stuff.
    {
        "tag": "Q2_high_cond_by_family_T12",
        "body": {
            "question":
                "Focus on well-established solid electrolyte Families in this dataset, such as "
                "Garnet, NASICON(-like), LISICON / Thio-LISICON, Argyrodite, Halide, "
                "Anti-perovskite, Nitride & related, LGPS-type thiophosphates, "
                "Glasses & glass-ceramics / LIPON, and Perovskite. "
                "Within these Families, consider only entries with Tier = T1 or T2 and "
                "Conductivity_S__cm ≥ 1e-4 S/cm. STRICTLY obey these filters: "
                "do NOT include any entries with Tier other than T1 or T2, and do NOT include "
                "any entries with Conductivity_S__cm < 1e-4 S/cm. "
                "For each Family that has at least one entry satisfying these conditions, list up to three "
                "representative entries and report: NewID, ChemFormula, Family, Conductivity_S__cm, "
                "Temperature__C, Tier, and best_mpid. "
                "If a given Family has no entries that meet the Tier and conductivity conditions, "
                "explicitly state that no such entries were found for that Family and do not list "
                "lower-Tier or lower-conductivity records. "
                "Then summarize in a few sentences which Families appear to reach the highest ionic "
                "conductivities in this high-confidence subset and what the typical order-of-magnitude "
                "ranges are for those Families.",
            "k": 100,
            "top_n": 40
        }
    },
]


# -------------------------
# Robust runner
# -------------------------
def run_one(tag, body, timeout_s=600, retries=3):
    """
    Sends one POST /ask request.
    - timeout_s: long timeout because local Llama can be slow on long prompts
    - retries: automatic retries for transient slowdowns
    """
    last_err = None

    for attempt in range(1, retries + 1):
        try:
            r = requests.post(API, json=body, timeout=timeout_s)
            r.raise_for_status()
            out = r.json()

            Path("outputs").mkdir(exist_ok=True)

            with open(f"outputs/{tag}.json", "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tag": tag,
                        "request": body,
                        **out
                    },
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            print(f"Saved outputs/{tag}.json")
            return

        except Exception as e:
            last_err = e
            print(f"[{tag}] attempt {attempt}/{retries} failed: {e}")
            time.sleep(3)

    raise last_err


if __name__ == "__main__":
    for q in QUESTIONS:
        run_one(q["tag"], q["body"])
        time.sleep(0.5)

    print("\nAll demo questions completed.")
