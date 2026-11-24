"""GEO tools: series/sample metadata and NCBI-generated RNA-seq count matrices.

NCBI re-processes most human/mouse bulk RNA-seq in GEO through one uniform
pipeline (HISAT2 -> featureCounts on GRCh38/GRCm39), which gives the agent a
consistent starting point regardless of how the original authors processed it.
"""
import html
import re
from collections import Counter, defaultdict

import pandas as pd
import requests

from .. import config
from .registry import RunContext, tool

GEO_ACC = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
GEO_DL = "https://www.ncbi.nlm.nih.gov/geo/download/"
GENE_INFO = {
    "human": "https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Homo_sapiens.gene_info.gz",
    "mouse": "https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Mus_musculus.gene_info.gz",
}


def _get(url, **params) -> requests.Response:
    r = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT,
                     headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    r.encoding = "utf-8"  # GEO serves UTF-8 but omits the charset header
    return r


def _parse_soft(text: str) -> list[dict]:
    """Parse GEO SOFT text into a list of entity records (^SERIES / ^SAMPLE blocks)."""
    records, cur = [], None
    for line in text.splitlines():
        if line.startswith("^"):
            cur = {"_id": line.split("=", 1)[1].strip(), "_fields": defaultdict(list)}
            records.append(cur)
        elif line.startswith("!") and cur is not None and " = " in line:
            k, v = line[1:].split(" = ", 1)
            cur["_fields"][k].append(v.strip())
    return records


def load_samples(gse: str) -> pd.DataFrame:
    """Sample sheet: one row per GSM with every characteristic as a column."""
    cache = config.DATA_DIR / f"{gse}_samples.soft"
    if not cache.exists():
        cache.write_text(_get(GEO_ACC, acc=gse, targ="gsm", form="text", view="brief").text,
                         encoding="utf-8")
    rows = []
    for rec in _parse_soft(cache.read_text(encoding="utf-8")):
        f = rec["_fields"]
        row = {"gsm": rec["_id"], "title": (f.get("Sample_title") or [""])[0]}
        for ch in f.get("Sample_characteristics_ch1", []):
            if ":" in ch:
                k, v = ch.split(":", 1)
                row[k.strip().lower()] = v.strip()
        rows.append(row)
    return pd.DataFrame(rows)


def _count_files(gse: str) -> dict:
    page = _get(GEO_DL, type="rnaseq_counts", acc=gse).text
    links = [html.unescape(h) for h in re.findall(r'href="(/geo/download/\?[^"]+)"', page)]
    out = {}
    for link in links:
        if "raw_counts" in link:
            out["raw_counts"] = "https://www.ncbi.nlm.nih.gov" + link
    if "raw_counts" in out:
        m = re.search(r"(GRC[hm]\d+(?:\.p\d+)?)", out["raw_counts"])
        out["genome_build"] = m.group(1) if m else "unknown"
        # GEO's own annotation file sits behind a captcha; use NCBI's official gene_info
        # (same NCBI GeneIDs) from the public FTP instead.
        out["annotation"] = GENE_INFO["mouse" if out["genome_build"].startswith("GRCm") else "human"]
    return out


@tool(
    "get_geo_series",
    "Get GEO series metadata: title, summary, overall design, and every sample with its "
    "characteristics (treatment, cell line, etc.). Also reports whether an NCBI-generated "
    "RNA-seq raw count matrix exists and its genome build.",
    {"gse": {"type": "string", "description": "GEO series accession, e.g. GSE52778"}},
    ["gse"],
)
def get_geo_series(ctx: RunContext, gse: str) -> dict:
    gse = gse.strip().upper()
    series = _parse_soft(_get(GEO_ACC, acc=gse, targ="self", form="text", view="brief").text)
    if not series:
        return {"error": f"{gse} not found in GEO"}
    f = series[0]["_fields"]
    samples = load_samples(gse)
    char_cols = [c for c in samples.columns if c not in ("gsm", "title")]
    files = _count_files(gse)
    ctx.state.setdefault("geo", {})[gse] = {"count_files": files}
    return {
        "gse": gse,
        "title": (f.get("Series_title") or [""])[0],
        "summary": " ".join(f.get("Series_summary", []))[:1500],
        "overall_design": " ".join(f.get("Series_overall_design", []))[:800],
        "platform": f.get("Series_platform_id", []),
        "n_samples": len(samples),
        "characteristic_fields": {c: dict(Counter(samples[c].fillna("NA"))) for c in char_cols},
        "samples": samples.head(60).to_dict(orient="records"),
        "ncbi_raw_counts_available": "raw_counts" in files,
        "genome_build": files.get("genome_build"),
    }


@tool(
    "download_count_matrix",
    "Download the NCBI-generated raw RNA-seq count matrix (genes x samples) and gene "
    "annotation for a GEO series. Requires human approval (external data download).",
    {"gse": {"type": "string", "description": "GEO series accession"}},
    ["gse"],
    requires_approval=True,
)
def download_count_matrix(ctx: RunContext, gse: str) -> dict:
    gse = gse.strip().upper()
    files = ctx.state.get("geo", {}).get(gse, {}).get("count_files") or _count_files(gse)
    if "raw_counts" not in files:
        return {"error": f"No NCBI-generated count matrix for {gse}. Raw FASTQ re-alignment "
                         "would be needed (out of scope for this pilot)."}
    paths = {}
    for kind in ("raw_counts", "annotation"):
        name = re.search(r"file=([^&]+)", files[kind]) or re.search(r"([^/]+)$", files[kind])
        name = name.group(1)
        path = config.DATA_DIR / name
        if not path.exists():
            path.write_bytes(_get(files[kind]).content)
        paths[kind] = path
    counts = pd.read_csv(paths["raw_counts"], sep="\t", index_col=0)
    ctx.state.setdefault("geo", {})[gse] = {"count_files": files, "paths": paths}
    return {
        "gse": gse,
        "genes": counts.shape[0],
        "samples": counts.shape[1],
        "sample_ids": list(counts.columns)[:60],
        "genome_build": files.get("genome_build"),
        "pipeline": "NCBI GEO RNA-seq pipeline (HISAT2 alignment, featureCounts, NCBI annotation)",
        "file": paths["raw_counts"].name,
        "size_mb": round(paths["raw_counts"].stat().st_size / 1e6, 2),
    }
