"""Literature tools: resolve a paper and pull its methods/results text.

Source: Europe PMC REST API (free, no key) which mirrors PubMed + PMC full text.
"""
import re
import xml.etree.ElementTree as ET

import requests

from .. import config
from .registry import RunContext, tool

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
ACCESSION_RE = re.compile(r"\b(GSE\d{3,}|GSM\d{3,}|SRP\d{4,}|SRR\d{4,}|PRJNA\d{3,}|E-MTAB-\d+|E-GEOD-\d+)\b")


def _get(url: str, **params) -> requests.Response:
    r = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT,
                     headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    return r


def _query_for(identifier: str) -> str:
    ident = identifier.strip()
    ident = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", ident, flags=re.I)
    if re.fullmatch(r"\d{5,9}", ident):
        return f"EXT_ID:{ident} AND SRC:MED"
    if re.fullmatch(r"PMC\d+", ident, flags=re.I):
        return f"PMCID:{ident.upper()}"
    if ident.startswith("10."):
        return f'DOI:"{ident}"'
    return ident  # free-text title search as a fallback


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


@tool(
    "resolve_paper",
    "Resolve a paper from a PMID, PMCID, DOI, or title. Returns title, journal, year, "
    "abstract, PMCID and whether open-access full text is available.",
    {"identifier": {"type": "string", "description": "PMID, PMCID, DOI or title"}},
    ["identifier"],
)
def resolve_paper(ctx: RunContext, identifier: str) -> dict:
    data = _get(f"{EPMC}/search", query=_query_for(identifier), resultType="core",
                format="json", pageSize=1).json()
    hits = data.get("resultList", {}).get("result", [])
    if not hits:
        return {"error": f"No paper found for '{identifier}'"}
    h = hits[0]
    paper = {
        "title": h.get("title"),
        "authors": h.get("authorString", "")[:200],
        "journal": h.get("journalInfo", {}).get("journal", {}).get("title"),
        "year": h.get("pubYear"),
        "pmid": h.get("pmid"),
        "pmcid": h.get("pmcid"),
        "doi": h.get("doi"),
        "open_access_full_text": h.get("isOpenAccess") == "Y" and bool(h.get("pmcid")),
        "abstract": re.sub(r"<[^>]+>", "", h.get("abstractText", "")),
    }
    paper["accessions_in_abstract"] = sorted(set(ACCESSION_RE.findall(paper["abstract"])))
    ctx.state["paper"] = paper
    return paper


@tool(
    "get_paper_sections",
    "Fetch open-access full text for a PMCID and return the Methods, Results and "
    "data-availability text plus every dataset accession (GSE/SRP/PRJNA/E-MTAB) found.",
    {"pmcid": {"type": "string", "description": "PubMed Central ID, e.g. PMC4057123"}},
    ["pmcid"],
)
def get_paper_sections(ctx: RunContext, pmcid: str) -> dict:
    cache = config.DATA_DIR / f"{pmcid}.xml"
    if not cache.exists():
        cache.write_bytes(_get(f"{EPMC}/{pmcid}/fullTextXML").content)
    root = ET.fromstring(cache.read_bytes())

    sections = {"methods": [], "results": [], "data_availability": []}
    # top-level sections only, so nested subsections aren't counted twice
    top = root.findall(".//body/sec") + root.findall(".//back/sec") + root.findall(".//back/notes")
    for sec in top:
        title = _text(sec.find("title")).lower()
        body = _text(sec)
        if any(k in title for k in ("method", "materials")):
            sections["methods"].append(body)
        elif any(k in title for k in ("result", "discussion")):
            sections["results"].append(body)
        elif any(k in title for k in ("data avail", "accession", "data access")):
            sections["data_availability"].append(body)

    full = _text(root)
    limits = {"methods": 10000, "results": 8000, "data_availability": 1500}
    out = {k: " ".join(v)[:limits[k]] for k, v in sections.items()}
    out["accessions_found"] = sorted(set(ACCESSION_RE.findall(full)))
    out["note"] = "Sections truncated for length." if len(" ".join(sections["methods"])) > 10000 else ""
    ctx.state["paper_accessions"] = out["accessions_found"]
    ctx.state["paper_text"] = full
    return out


@tool(
    "register_published_claims",
    "PRE-REGISTER the paper's findings BEFORE any data is analysed (blinded, like a trial "
    "protocol). Pass genes the paper explicitly reports as changed, formatted 'GENE:up' or "
    "'GENE:down', plus the DE gene count and FDR the paper reports (0 if not stated). Each gene "
    "is checked against the paper text; genes not found in the paper are rejected.",
    {
        "claims": {"type": "array", "items": {"type": "string"},
                   "description": "e.g. ['CRISPLD2:up', 'KCTD12:down']"},
        "reported_de_gene_count": {"type": "integer", "description": "0 if not reported"},
        "reported_fdr": {"type": "number", "description": "FDR cutoff used in the paper, e.g. 0.05"},
    },
    ["claims"],
)
def register_published_claims(ctx: RunContext, claims: list[str], reported_de_gene_count: int = 0,
                              reported_fdr: float = 0.05) -> dict:
    if "de" in ctx.state:
        return {"error": "Claims must be registered before analysis; DE has already run."}
    text = ctx.state.get("paper_text") or ctx.state.get("paper", {}).get("abstract", "")
    accepted, rejected = [], []
    for c in claims:
        gene, _, direction = c.partition(":")
        gene, direction = gene.strip().upper(), direction.strip().lower()
        if direction not in ("up", "down"):
            rejected.append({"claim": c, "reason": "direction must be up or down"})
        elif not re.search(rf"\b{re.escape(gene)}\b", text):
            rejected.append({"claim": c, "reason": "gene not mentioned in paper text"})
        else:
            accepted.append(f"{gene}:{direction}")
    ctx.state["claims"] = {"claims": accepted, "rejected": rejected,
                           "reported_de_gene_count": reported_de_gene_count or 0,
                           "reported_fdr": reported_fdr or 0.05}
    return {"registered": accepted, "rejected": rejected,
            "note": "Claims are now locked. Proceed to data retrieval and analysis."}
