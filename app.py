"""Demo UI:  streamlit run app.py"""
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lit2analysis import config, pipeline

st.set_page_config(page_title="Literature-to-Analysis Agent", page_icon="🧬", layout="wide")

EXAMPLES = {
    "Himes 2014 · Dexamethasone in airway smooth muscle (PMID 24926665)": "24926665",
    "Custom (PMID / PMCID / DOI)": "",
}


# ---------------------------------------------------------------- helpers
def list_runs() -> list[Path]:
    return sorted([p for p in config.RUNS_DIR.iterdir() if (p / "trace.jsonl").exists()], reverse=True)


def load_trace(run_dir: Path) -> list[dict]:
    return [json.loads(l) for l in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines() if l]


def short(obj, n=1200) -> str:
    s = json.dumps(obj, default=str, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " …"


def render_event(e: dict, box) -> None:
    t = e["type"]
    with box:
        if t == "task":
            st.info(f"**Task:** {e['text']}  \nModel: `{e['model']}` · Tools: {', '.join(e['tools'])}")
        elif t == "thought":
            with st.expander(f"🧠 Reasoning · step {e['step']}", expanded=False):
                st.markdown(e["text"])
        elif t == "tool_call":
            st.markdown(f"🔧 **Step {e['step']} → `{e['tool']}`** `{short(e['args'], 300)}`")
        elif t == "tool_result":
            r = e["result"]
            icon = "❌" if isinstance(r, dict) and "error" in r else "✅"
            with st.expander(f"{icon} Result from `{e['tool']}`", expanded=False):
                st.code(short(r, 4000), language="json")
        elif t == "approval":
            (st.success if e["approved"] else st.error)(
                f"👤 Human-in-the-loop gate: `{e['tool']}` → **{'APPROVED' if e['approved'] else 'DECLINED'}**")
        elif t == "retry":
            st.caption(f"⏳ {e['model']}: {e['reason']} — failing over / retrying")
        elif t == "final":
            st.markdown("---\n### 📝 Agent report (draft)")
            st.markdown(e["text"])
        elif t == "critic_start":
            st.caption("🔎 Independent critic model reviewing the report against raw evidence…")
        elif t == "critic":
            with st.container(border=True):
                st.markdown("#### 🔎 QA critic (LLM-as-judge)")
                st.markdown(e["text"])
        elif t == "report":
            st.success(f"Report + audit trail saved to `{Path(e['path']).parent.name}/`")


def volcano(run_dir: Path) -> None:
    csvs = list(run_dir.glob("*_DE_*.csv"))
    if not csvs:
        return
    df = pd.read_csv(csvs[0]).dropna(subset=["padj"])
    floor = df.loc[df.padj > 0, "padj"].min()
    df["neg_log10_padj"] = -np.log10(df.padj.clip(lower=floor))
    claims = []
    for e in load_trace(run_dir):
        if e["type"] == "tool_result" and e["tool"] == "register_published_claims":
            claims = [c.split(":")[0] for c in e["result"].get("registered", [])]
    df["class"] = np.where(df.symbol.isin(claims), "Published claim",
                           np.where(df.padj < 0.05, "FDR < 0.05", "n.s."))
    fig = px.scatter(df.sort_values("class", ascending=False), x="log2FoldChange", y="neg_log10_padj",
                     color="class", hover_name="symbol", opacity=0.7,
                     color_discrete_map={"Published claim": "#d62728", "FDR < 0.05": "#1f77b4",
                                         "n.s.": "#c7c7c7"},
                     labels={"neg_log10_padj": "-log10(adjusted p)", "log2FoldChange": "log2 fold change"})
    hl = df[df["class"] == "Published claim"]
    fig.add_scatter(x=hl.log2FoldChange, y=hl.neg_log10_padj, text=hl.symbol, mode="text",
                    textposition="top center", showlegend=False)
    fig.update_layout(height=480, legend_title=None, margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"{len(df):,} genes with an adjusted p-value · red = genes pre-registered from the paper · file `{csvs[0].name}`")


def signoff(run_dir: Path) -> None:
    f = run_dir / "signoff.json"
    if f.exists():
        s = json.loads(f.read_text())
        (st.success if s["decision"] == "APPROVED" else st.error)(
            f"**{s['decision']}** by {s['reviewer']} at {s['ts']}" + (f" — {s['comment']}" if s["comment"] else ""))
        return
    st.markdown("#### 👤 Human sign-off (required before anything is cited)")
    c1, c2 = st.columns([1, 2])
    reviewer = c1.text_input("Reviewer", key=f"rev_{run_dir.name}")
    comment = c2.text_input("Comment", key=f"com_{run_dir.name}")
    b1, b2, _ = st.columns([1, 1, 4])
    for decision, text, kind, col in (("APPROVED", "Approve", "primary", b1),
                                      ("REJECTED", "Reject", "secondary", b2)):
        if col.button(text, key=f"{decision}_{run_dir.name}", type=kind, disabled=not reviewer):
            rec = {"decision": decision, "reviewer": reviewer, "comment": comment,
                   "ts": datetime.now().isoformat(timespec="seconds")}
            f.write_text(json.dumps(rec, indent=2))
            with (run_dir / "trace.jsonl").open("a", encoding="utf-8") as t:
                t.write(json.dumps({"type": "human_signoff", "run_id": run_dir.name, **rec}) + "\n")
            st.rerun()


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🧬 Lit-to-Analysis Agent")
    st.caption("Pilot · reproduces published transcriptomic findings from public data")
    mode = st.radio("Mode", ["Live run", "Replay a recorded run"], horizontal=False)
    st.divider()
    if mode == "Live run":
        choice = st.selectbox("Paper", list(EXAMPLES))
        paper = st.text_input("Identifier", EXAMPLES[choice] or "", placeholder="PMID, PMCID or DOI")
        preapprove = st.toggle("Approve external data download", value=True,
                               help="Human-in-the-loop gate. Turn off to see the agent stop at the gate.")
        go = st.button("▶ Run agent", type="primary", use_container_width=True, disabled=not paper)
    else:
        runs = list_runs()
        run_pick = st.selectbox("Recorded run", runs, format_func=lambda p: p.name) if runs else None
        speed = st.slider("Replay delay (s/event)", 0.0, 2.0, 0.6, 0.1)
        go = st.button("▶ Replay", type="primary", use_container_width=True, disabled=not runs)
    st.divider()
    st.caption(f"LLM: {config.LLM_PROVIDER} · `{config.ACTIVE_MODEL}`  \nData: Europe PMC · NCBI GEO  \nStats: PyDESeq2")

tab_run, tab_results, tab_arch = st.tabs(["🤖 Agent trace", "📊 Results & sign-off", "🏗️ Architecture"])

# ---------------------------------------------------------------- run / replay
with tab_run:
    if go and mode == "Live run":
        box = st.container()
        with st.status("Agent working…", expanded=True) as status:
            try:
                ctx = pipeline.run(paper, on_event=lambda e: render_event(e, box),
                                   approver=lambda tool, args: preapprove)
                st.session_state["run_dir"] = str(ctx.run_dir)
                status.update(label="Done — see Results & sign-off tab", state="complete")
            except Exception as ex:
                status.update(label=f"Stopped: {ex}", state="error")
                st.warning("Free-tier LLM capacity can be flaky. Switch to **Replay a recorded run** in the sidebar.")
    elif go and mode != "Live run" and run_pick:
        box = st.container()
        with st.status(f"Replaying {run_pick.name}…", expanded=True) as status:
            for e in load_trace(run_pick):
                if e["type"] != "human_signoff":
                    render_event(e, box)
                    time.sleep(speed if e["type"] not in ("retry", "thought") else speed / 4)
            status.update(label="Replay complete — see Results & sign-off tab", state="complete")
        st.session_state["run_dir"] = str(run_pick)
    elif "run_dir" in st.session_state:
        for e in load_trace(Path(st.session_state["run_dir"])):
            if e["type"] != "human_signoff":
                render_event(e, st.container())
    else:
        st.markdown("### Give the agent a paper. It will:")
        st.markdown(
            "1. **Read** the paper (Europe PMC full text)\n"
            "2. **Pre-register** the published claims *before* touching data (blinded)\n"
            "3. **Find** the GEO dataset and map samples to the paper's comparison\n"
            "4. **Ask a human** before downloading external data\n"
            "5. **Re-run** differential expression (DESeq2) on NCBI-reprocessed counts\n"
            "6. **Score** match vs. mismatch with deterministic code, not the LLM\n"
            "7. **Explain** divergences (genome build, pipeline, thresholds)\n"
            "8. **Self-audit** with an independent critic, then wait for **human sign-off**")

with tab_results:
    if "run_dir" not in st.session_state:
        st.info("Run or replay the agent first.")
    else:
        rd = Path(st.session_state["run_dir"])
        cmp_ = next((e["result"] for e in load_trace(rd)
                     if e["type"] == "tool_result" and e["tool"] == "compare_with_published"), None)
        if cmp_ and "verdict" in cmp_:
            c = st.columns(4)
            c[0].metric("Verdict", cmp_["verdict"])
            c[1].metric("Claims confirmed", cmp_["claims_confirmed"])
            c[2].metric("DE genes (ours)", f"{cmp_['our_de_gene_count_at_reported_fdr']:,}")
            c[3].metric("DE genes (paper)", cmp_["reported_de_gene_count"] or "n/a")
            tbl = pd.DataFrame(cmp_["per_gene"])
            if "padj" in tbl:
                tbl["padj"] = tbl["padj"].map(lambda v: f"{v:.2e}" if pd.notna(v) else "")
            st.dataframe(tbl, use_container_width=True, hide_index=True)
        volcano(rd)
        signoff(rd)
        if (rd / "report.md").exists():
            st.download_button("⬇ Download full report (markdown)", (rd / "report.md").read_text(encoding="utf-8"),
                               file_name=f"reproduction_report_{rd.name}.md")
            with st.expander("Full report with provenance"):
                st.markdown((rd / "report.md").read_text(encoding="utf-8"))

with tab_arch:
    st.graphviz_chart("""
digraph G {
  rankdir=LR; node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 fillcolor="#eef3fb"];
  user [label="Bioinformatician\\n(PMID / DOI)" shape=oval fillcolor="#fff4d6"];
  subgraph cluster_agent { label="Reproduction Agent (reason → act → observe loop)"; style=dashed;
    llm [label="LLM planner\\n(Bedrock Nova Pro, swappable)" fillcolor="#dbe8ff"];
    guard [label="Guardrails\\nmax steps · blinding rule\\nschema-validated tools" fillcolor="#ffe3e3"]; }
  subgraph cluster_tools { label="Tools (MCP-ready contracts)"; style=dashed;
    t1 [label="resolve_paper\\nget_paper_sections\\n(Europe PMC)"];
    t2 [label="register_published_claims\\n(blinded pre-registration)"];
    t3 [label="get_geo_series\\ndownload_count_matrix\\n(NCBI GEO)"];
    t4 [label="run_differential_expression\\n(PyDESeq2)"];
    t5 [label="compare_with_published\\n(deterministic verdict)"]; }
  hitl [label="👤 Human approval\\n(data download)" fillcolor="#fff4d6"];
  critic [label="Critic model\\n(LLM-as-judge QA)" fillcolor="#e8dcff"];
  report [label="Report + provenance\\n(genome build, params, versions)"];
  audit [label="Audit trail\\ntrace.jsonl" shape=cylinder fillcolor="#e6f5e6"];
  signoff [label="👤 Human sign-off" fillcolor="#fff4d6"];
  user -> llm; llm -> guard -> {t1 t2 t3 t4 t5}; t3 -> hitl [style=dotted label="gated"];
  llm -> critic -> report -> signoff; llm -> audit [style=dotted]; critic -> audit [style=dotted];
}""", use_container_width=True)
    c1, c2 = st.columns(2)
    c1.markdown("""**Design principles**
- **LLM for judgment, code for numbers.** The model picks samples, contrast and claims. Code computes every statistic and the verdict.
- **Blinded:** claims are locked before data is analysed; genes not found in the paper are rejected.
- **Human-in-the-loop** at data download and at final sign-off.
- **Full provenance:** genome build, pipeline, parameters, model and software versions in every report.
- **Append-only audit trail** of every thought, tool call, approval and result.""")
    c2.markdown("""**Path to production**
| Pilot (today) | Production |
|---|---|
| Gemini free tier | Enterprise LLM endpoint (Copilot Studio / Cortex) |
| Python tool registry | Same contracts exposed as **MCP servers** |
| NCBI-reprocessed counts | Nextflow nf-core/rnaseq from raw FASTQ |
| Streamlit | Teams approval cards + SharePoint reports |
| Local trace.jsonl | Central logging / AI Registry evidence |""")
