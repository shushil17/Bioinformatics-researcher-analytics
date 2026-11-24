"""Analysis + verification tools.

Division of labour (the key governance idea of this pilot):
  * The LLM decides WHAT to compare (which samples, which contrast, which claims).
  * Deterministic code does the statistics and scores the match - the model never
    computes or "estimates" a number that ends up in the report.
"""
import re
import warnings

import numpy as np
import pandas as pd

from .geo import load_samples
from .registry import RunContext, tool

warnings.filterwarnings("ignore")


def _safe(v: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(v)).strip("_") or "NA"


@tool(
    "run_differential_expression",
    "Run DESeq2 (PyDESeq2) differential expression on the downloaded count matrix. You "
    "choose the sample grouping from GEO characteristics: which field defines the groups, "
    "which value is control vs treatment, and optionally a pairing field (e.g. donor or "
    "cell line) for a paired design. Samples in other groups are excluded.",
    {
        "gse": {"type": "string"},
        "group_field": {"type": "string", "description": "Characteristic column, e.g. 'treatment'"},
        "control_value": {"type": "string", "description": "Exact value for the control group"},
        "treatment_value": {"type": "string", "description": "Exact value for the treatment group"},
        "pair_field": {"type": "string", "description": "Optional blocking field, e.g. 'cell line'. Empty for none."},
    },
    ["gse", "group_field", "control_value", "treatment_value"],
)
def run_differential_expression(ctx: RunContext, gse: str, group_field: str, control_value: str,
                                treatment_value: str, pair_field: str = "") -> dict:
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    gse = gse.strip().upper()
    if not ctx.state.get("claims", {}).get("claims"):
        return {"error": "Blinding rule: call register_published_claims before running any analysis."}
    paths = ctx.state.get("geo", {}).get(gse, {}).get("paths")
    if not paths:
        return {"error": "Count matrix not downloaded yet - call download_count_matrix first."}

    meta = load_samples(gse).set_index("gsm")
    group_field, pair_field = group_field.lower().strip(), (pair_field or "").lower().strip()
    if group_field not in meta.columns:
        return {"error": f"'{group_field}' not a characteristic. Options: {list(meta.columns)}"}
    meta = meta[meta[group_field].isin([control_value, treatment_value])].copy()
    if meta[group_field].nunique() < 2:
        return {"error": f"Need both groups; found {meta[group_field].value_counts().to_dict()}"}

    counts = pd.read_csv(paths["raw_counts"], sep="\t", index_col=0)
    meta = meta.loc[[s for s in meta.index if s in counts.columns]]
    counts = counts[meta.index].T                      # samples x genes
    counts = counts.loc[:, counts.sum(axis=0) >= 10]   # standard low-count prefilter

    design_df = pd.DataFrame(index=meta.index)
    design_df["condition"] = meta[group_field].map(
        {control_value: "control", treatment_value: "treatment"})
    design = "~condition"
    if pair_field and pair_field in meta.columns:
        design_df["pair"] = meta[pair_field].map(_safe)
        design = "~pair + condition"

    dds = DeseqDataSet(counts=counts, metadata=design_df, design=design, quiet=True)
    dds.deseq2()
    stats = DeseqStats(dds, contrast=["condition", "treatment", "control"], quiet=True)
    stats.summary()
    res = stats.results_df.copy()

    # NCBI gene_info: col 1 = GeneID, col 2 = Symbol
    annot = pd.read_csv(paths["annotation"], sep="\t", usecols=[1, 2], index_col=0).iloc[:, 0]
    annot.index = annot.index.astype(str)
    ids = res.index.astype(str)
    res.insert(0, "symbol", annot.reindex(ids).fillna(pd.Series(ids, index=ids)).values)
    res = res.sort_values("padj")
    out_csv = ctx.run_dir / f"{gse}_DE_{_safe(treatment_value)}_vs_{_safe(control_value)}.csv"
    res.to_csv(out_csv)

    sig = res[(res.padj < 0.05)]
    ctx.state["de"] = {"gse": gse, "results": res, "csv": out_csv, "params": {
        "group_field": group_field, "control": control_value, "treatment": treatment_value,
        "pair_field": pair_field or None, "design": design, "n_samples": len(design_df),
        "samples": design_df.assign(group=meta[group_field]).reset_index().to_dict("records"),
        "genes_tested": int(res.shape[0]), "method": "PyDESeq2 Wald test, BH-adjusted"}}

    top = lambda d: d.head(15)[["symbol", "log2FoldChange", "padj"]].round(4).to_dict("records")
    return {
        "design": design,
        "samples_used": design_df["condition"].value_counts().to_dict(),
        "genes_tested": int(res.shape[0]),
        "significant_fdr_0.05": int(len(sig)),
        "up": int((sig.log2FoldChange > 0).sum()),
        "down": int((sig.log2FoldChange < 0).sum()),
        "top_up": top(sig[sig.log2FoldChange > 0]),
        "top_down": top(sig[sig.log2FoldChange < 0]),
        "results_file": out_csv.name,
    }


@tool(
    "compare_with_published",
    "Score the DE results against the PRE-REGISTERED claims. Returns a deterministic per-gene "
    "table and a verdict (REPRODUCED / PARTIALLY REPRODUCED / NOT REPRODUCED).",
    {},
)
def compare_with_published(ctx: RunContext) -> dict:
    de, reg = ctx.state.get("de"), ctx.state.get("claims")
    if not de or not reg:
        return {"error": "Need registered claims and DE results first."}
    claims, reported_de_gene_count = reg["claims"], reg["reported_de_gene_count"]
    res = de["results"]
    by_sym = res.reset_index().drop_duplicates("symbol").set_index("symbol")
    fdr = reg["reported_fdr"]

    rows = []
    for c in claims:
        gene, _, direction = c.partition(":")
        gene, direction = gene.strip().upper(), (direction.strip().lower() or "up")
        if gene not in by_sym.index:
            rows.append({"gene": gene, "claimed": direction, "status": "NOT FOUND in annotation"})
            continue
        r = by_sym.loc[gene]
        lfc, padj = float(r.log2FoldChange), float(r.padj) if pd.notna(r.padj) else np.nan
        observed = "up" if lfc > 0 else "down"
        significant = bool(padj < fdr) if pd.notna(padj) else False
        status = ("CONFIRMED" if observed == direction and significant else
                  "SAME DIRECTION, NOT SIGNIFICANT" if observed == direction else
                  "OPPOSITE DIRECTION")
        rows.append({"gene": gene, "claimed": direction, "observed": observed,
                     "log2FC": round(lfc, 3), "padj": float(f"{padj:.3g}") if pd.notna(padj) else None,
                     "status": status})

    n = len(rows)
    confirmed = sum(r["status"] == "CONFIRMED" for r in rows)
    rate = confirmed / n if n else 0.0
    verdict = ("REPRODUCED" if rate >= 0.8 else "PARTIALLY REPRODUCED" if rate >= 0.5
               else "NOT REPRODUCED")
    ours = int((res.padj < fdr).sum())
    result = {
        "verdict": verdict,
        "claims_confirmed": f"{confirmed}/{n}",
        "confirmation_rate": round(rate, 3),
        "per_gene": rows,
        "our_de_gene_count_at_reported_fdr": ours,
        "reported_de_gene_count": reported_de_gene_count or None,
        "claims_rejected_at_registration": reg["rejected"],
        "verdict_rule": ">=80% claims confirmed = REPRODUCED; >=50% = PARTIAL; else NOT REPRODUCED",
    }
    ctx.state["comparison"] = result
    return result
