#!/usr/bin/env python3
"""
make_figures.py — regenerates the manuscript figures that aggregate over the whole dataset.

    python make_figures.py --master ../data/final/sse_conductivity_master.csv --out figures/

Figures produced (file names match the manuscript's \\includegraphics calls):
  DefFig1.png      (a) entries per source, (b) entries per tier, (c) tier composition within source
  DefFig2.png      structural-family assignment: per-source bars + overall doughnut
  DefFigCov1.png   experimental entries per MP-ID, full range (bins of 20)
  DefFigCov2.png   same, zoom on 1–21 entries
  Fig7_Bar_Element_Top20.png  twenty most frequent elements (counted once per entry)

Every number printed on a figure is also written to <out>/figure_values.json so the
text of the manuscript can be checked against the figures mechanically.
"""
import argparse, json, re
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Palette: identical to the other (unchanged) figures of the manuscript, for internal consistency.
TIER = {"T1": "#E36C09", "T2": "#0070C0", "T3": "#8B0000", "T4": "#0B3D3D"}
SRC = {"Obelix": "#4CA62A", "Li Ion": "#0B3A4E", "Shon et al.": "#A0461A"}
ASSIGNED, UNASSIGNED, ACCENT = "#ED7D31", "#1F5F7A", "#ED7D31"
SRC_LABEL = {"OBELiX": "Obelix", "Liverpool Ionics": "Li Ion", "Shon et al. (2023)": "Shon et al."}
SRC_ORDER = ["Obelix", "Li Ion", "Shon et al."]
TXT = "#222222"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": "#444444",
                     "axes.labelcolor": TXT, "xtick.color": TXT, "ytick.color": TXT, "text.color": TXT,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#E6E6E6", "grid.linewidth": 0.8, "axes.axisbelow": True, "savefig.dpi": 300})

def load(path):
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    d["src"] = d["source_label"].map(SRC_LABEL)
    return d

def fig1(d, out, V):
    fig, axs = plt.subplot_mosaic([["a", "b"], ["c", "c"]], figsize=(11, 9.5), height_ratios=[1, 1.05])
    # (a) pie
    n = d["src"].value_counts().reindex(SRC_ORDER); V["fig1a_source_counts"] = n.to_dict()
    ax = axs["a"]; ax.grid(False)
    w, _ = ax.pie(n.values, colors=[SRC[s] for s in SRC_ORDER], startangle=90, counterclock=False,
                  wedgeprops=dict(linewidth=1.5, edgecolor="white"))
    for wedge, val in zip(w, n.values):
        ang = np.deg2rad((wedge.theta1 + wedge.theta2) / 2); r = 1.15
        ax.text(r * np.cos(ang), r * np.sin(ang), f"{val}", ha="center", va="center", fontweight="bold")
    ax.legend(w, SRC_ORDER, loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=3, frameon=False, fontsize=10)
    ax.set_title("(a) Entries per Database Source", fontweight="bold")
    # (b) tier bar
    t = d["Tier"].value_counts().reindex(["T1", "T2", "T3", "T4"]); N = len(d)
    V["fig1b_tier_counts"] = t.to_dict(); V["fig1b_tier_pct"] = {k: round(v / N * 100, 1) for k, v in t.items()}
    ax = axs["b"]; ax.grid(axis="x", visible=False)
    ax.bar(t.index, t.values, color=[TIER[k] for k in t.index], width=0.45, edgecolor="#333333", linewidth=0.6)
    for i, (k, v) in enumerate(t.items()):
        ax.text(i, v + N * 0.012, f"{v / N * 100:.1f}%, {v}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylim(0, max(3000, t.max() * 1.15)); ax.set_ylabel("Number of entries"); ax.set_xlabel("Tier")
    ax.set_title("(b) Distribution of Entries by Matching Tier", fontweight="bold")
    # (c) tier within source
    ct = pd.crosstab(d["src"], d["Tier"]).reindex(index=SRC_ORDER, columns=["T1", "T2", "T3", "T4"]).fillna(0)
    pct = ct.div(ct.sum(axis=1), axis=0) * 100; V["fig1c_tier_within_source_pct"] = pct.round(2).to_dict(orient="index")
    ax = axs["c"]; ax.grid(axis="x", visible=False); x = np.arange(len(SRC_ORDER)); wdt = 0.19
    for j, tier in enumerate(["T1", "T2", "T3", "T4"]):
        vals = pct[tier].values; xs = x + (j - 1.5) * wdt
        ax.bar(xs, vals, width=wdt * 0.92, color=TIER[tier], edgecolor="#333333", linewidth=0.6, label=tier)
        for xi, v in zip(xs, vals):
            if v > 0: ax.text(xi, v + 1.2, f"{v:.2f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_xticks(x, SRC_ORDER); ax.set_ylim(0, 100); ax.set_yticks(range(0, 101, 20), [f"{v}%" for v in range(0, 101, 20)])
    ax.set_ylabel("Percentage of entries in source [%]"); ax.set_xlabel("Source database")
    ax.legend(ncol=4, frameon=False, loc="upper left"); ax.set_title("(c) Contribution of Each Source to Each Tier", fontweight="bold")
    fig.tight_layout(h_pad=2.5); fig.savefig(out / "DefFig1.png"); plt.close(fig)

def fig2(d, out, V):
    assigned = d["Family"].ne("Unassigned")
    by = assigned.groupby(d["src"]).mean().reindex(SRC_ORDER) * 100
    V["fig2_assigned_pct_by_source"] = by.round(2).to_dict(); V["fig2_assigned_pct_overall"] = round(assigned.mean() * 100, 1)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6.5), width_ratios=[1.05, 1])
    x = np.arange(len(SRC_ORDER)); w = 0.3; ax.grid(axis="x", visible=False)
    for xi, s in zip(x, SRC_ORDER):
        ua, a = 100 - by[s], by[s]
        ax.bar(xi - w / 2, ua, w * 0.9, color=UNASSIGNED, edgecolor="#333333", linewidth=0.6)
        ax.bar(xi + w / 2, a, w * 0.9, color=ASSIGNED, edgecolor="#333333", linewidth=0.6)
        ax.text(xi - w / 2, ua + 1.5, f"{ua:.2f}%", ha="center", fontsize=10, fontweight="bold")
        ax.text(xi + w / 2, a + 1.5, f"{a:.2f}%", ha="center", fontsize=10, fontweight="bold")
    ax.set_xticks(x, SRC_ORDER); ax.set_ylim(0, 108); ax.set_yticks(range(0, 101, 10), [f"{v}.00%" for v in range(0, 101, 10)])
    ax.set_ylabel("Percentage of entries in source [%]"); ax.set_xlabel("Source database")
    ax.set_title("Family Assignment Quality by Source", fontweight="bold")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=UNASSIGNED), plt.Rectangle((0, 0), 1, 1, color=ASSIGNED)],
              labels=["Unassigned", "Assigned"], loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
    ax2.grid(False); pa = V["fig2_assigned_pct_overall"]
    wedges, _ = ax2.pie([pa, 100 - pa], colors=[ASSIGNED, UNASSIGNED], startangle=65, counterclock=False,
                        wedgeprops=dict(width=0.38, edgecolor="white", linewidth=1.5))
    for wedge, lab in zip(wedges, [f"Assigned,\n{pa:.1f}%", f"Unassigned,\n{100 - pa:.1f}%"]):
        ang = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
        ax2.text(1.28 * np.cos(ang), 1.28 * np.sin(ang), lab, ha="left" if np.cos(ang) >= 0 else "right",
                 va="center", fontweight="bold", fontsize=10)
    ax2.set_title("Share of Entries with Assigned Structural Family", fontweight="bold")
    fig.tight_layout(); fig.savefig(out / "DefFig2.png"); plt.close(fig)

def _hist(labels, counts, title, out, name, ylim=300):
    fig, ax = plt.subplots(figsize=(9, 5.1)); ax.grid(axis="x", visible=False)
    ax.bar(range(len(labels)), counts, width=1.0, color=ACCENT, edgecolor="white", linewidth=0.8)
    for i, c in enumerate(counts): ax.text(i, c + ylim * 0.012, str(c), ha="center", fontsize=9, color="#555555")
    ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right", fontsize=9); ax.set_ylim(0, ylim)
    ax.set_xlabel("Experimental entries per MP-ID"); ax.set_ylabel("Count"); ax.set_title(title, fontweight="bold")
    fig.tight_layout(); fig.savefig(out / name); plt.close(fig)

def figcov(d, out, V):
    n = d["best_mpid"].value_counts()
    edges = list(range(1, 302, 20)); edges[0] = 0  # [1,21],(21,41],...,(281,301]
    counts = [int(((n > lo) & (n <= hi)).sum()) for lo, hi in zip(edges[:-1], edges[1:])]
    labels = ["[1, 21]"] + [f"({lo}, {hi}]" for lo, hi in zip(edges[1:-1], edges[2:])]
    V["figcov1_bins"] = dict(zip(labels, counts))
    _hist(labels, counts, "Distribution of Coverage per MP-ID", out, "DefFigCov1.png")
    zc = [int((n <= 2).sum())] + [int((n == k).sum()) for k in range(3, 22)] + [int((n > 21).sum())]
    zl = ["[1, 2]"] + [f"({k - 1}, {k}]" for k in range(3, 22)] + ["> 21"]
    V["figcov2_bins"] = dict(zip(zl, zc)); V["entries_per_mpid_max"] = int(n.max()); V["n_mpids"] = int(len(n))
    _hist(zl, zc, "Distribution of Coverage per MP-ID (Zoom)", out, "DefFigCov2.png")

def fig7(d, out, V):
    c = Counter(e for f in d["ChemFormula"] for e in set(re.findall(r"[A-Z][a-z]?", f)))
    top = c.most_common(20); V["fig7_top20_elements"] = dict(top)
    fig, ax = plt.subplots(figsize=(11, 7.5)); ax.grid(axis="y", visible=False)
    els = [e for e, _ in top][::-1]; vals = [v for _, v in top][::-1]
    # per-element colours: the manuscript's categorical palette (as in the July figure), cycled after 16
    PAL = ["#E36C09", "#0070C0", "#8B0000", "#0B3D3D", "#4B0082", "#FF69B4", "#33FF33", "#8B4513",
           "#6EB4FF", "#FFB6D9", "#B266FF", "#C6DCFF", "#FFFF80", "#009999", "#000000", "#9ACD32"]
    cols = [PAL[i % len(PAL)] for i in range(len(top))][::-1]
    ax.barh(els, vals, color=cols, edgecolor="#333333", linewidth=0.6, height=0.72)
    for i, v in enumerate(vals): ax.text(v + max(vals) * 0.008, i, str(v), va="center", fontsize=10, fontweight="bold")
    ax.set_xlabel("Number of entries"); ax.set_ylabel("Element"); ax.set_xlim(0, max(vals) * 1.08)
    ax.set_title("Top-20 Element Frequency in the SSE Conductivity Dataset", fontweight="bold")
    fig.tight_layout(); fig.savefig(out / "Fig7_Bar_Element_Top20.png"); plt.close(fig)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--master", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    d = load(a.master); V = {"n_rows": len(d)}
    fig1(d, out, V); fig2(d, out, V); figcov(d, out, V); fig7(d, out, V)
    json.dump(V, open(out / "figure_values.json", "w"), indent=1)
    print(json.dumps(V, indent=1))
