"""Builds presentation/Lit2Analysis_Agent_Pilot.pptx from the recorded demo run."""
import json
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).parent
RUN = HERE.parent / "runs" / "DEMO-himes2014-bedrock-nova"

INK, TEAL, MINT, AMBER, RED = "0E2A30", "12808C", "E3F1F0", "E8A33D", "C8553D"
GREY, WHITE, SOFT, PURPLE = "5B6B70", "FFFFFF", "F4F8F8", "7A5CC2"
HEAD, BODY = "Cambria", "Calibri"

# ---- evidence from the recorded run ------------------------------------------------
trace = [json.loads(l) for l in (RUN / "trace.jsonl").read_text(encoding="utf-8").splitlines() if l]
cmp_ = next(e["result"] for e in trace if e.get("tool") == "compare_with_published" and e["type"] == "tool_result")
de = next(e["result"] for e in trace if e.get("tool") == "run_differential_expression" and e["type"] == "tool_result")
genes = sorted(cmp_["per_gene"], key=lambda r: r["log2FC"])

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def rgb(h):
    return RGBColor.from_string(h)


def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = rgb(color)


def box(slide, x, y, w, h, fill=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line=None, radius=0.08):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1.25)
    else:
        s.line.fill.background()
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.shadow.inherit = False
    return s


def text(slide_or_shape, x=None, y=None, w=None, h=None, content="", size=16, color=INK, bold=False,
         font=BODY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False, space_after=0, margin=0.0):
    """content: str, or list of paragraphs; a paragraph is str or list of (text, {overrides}) runs."""
    if x is None:
        shape = slide_or_shape
    else:
        shape = slide_or_shape.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        runs = para if isinstance(para, list) else [(para, {})]
        for t, o in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = rgb(o.get("color", color))
    return shape


def arrow(slide, x1, y1, x2, y2, color=GREY, dashed=False, width=1.5):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    if dashed:
        etree.SubElement(ln, qn("a:prstDash"), val="dash")
    tail = etree.SubElement(ln, qn("a:tailEnd"))
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")
    return c


def circle_num(slide, x, y, d, label, fill=TEAL, color=WHITE, size=16):
    s = box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    text(s, content=label, size=size, color=color, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return s


def title(slide, t, sub=None, color=INK, size=34):
    text(slide, 0.6, 0.45, 12.1, 0.8, t, size=size, bold=True, font=HEAD, color=color)
    if sub:
        text(slide, 0.6, 1.2, 12.1, 0.5, sub, size=16, color=GREY if color == INK else "B9D3D6", italic=True)


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


# =========================================================== 1. Title
s = prs.slides.add_slide(BLANK)
bg(s, INK)
for i, (cx, cy, d, col) in enumerate([(9.6, 1.0, 2.6, TEAL), (11.2, 3.2, 1.6, AMBER), (9.0, 4.4, 1.2, "1E5A61")]):
    box(s, cx, cy, d, d, fill=col, shape=MSO_SHAPE.OVAL)
text(s, 0.8, 1.7, 8.4, 0.5, "AGENTIC AI PILOT PROPOSAL", size=14, color=AMBER, bold=True)
text(s, 0.8, 2.2, 8.6, 1.9, "Literature-to-Analysis Agent", size=48, bold=True, font=HEAD, color=WHITE)
text(s, 0.8, 3.95, 8.2, 1.2, "An AI agent that re-runs a published bioinformatics analysis from public data "
     "and reports whether the findings hold up.", size=20, color="CFE3E5")
text(s, 0.8, 5.9, 8.4, 0.5, "Working session  ·  Team + Manager  ·  Proposal + live demo", size=14, color="8FB3B8")
notes(s, "Open: one sentence on the pain (days per paper to trust a published result). "
         "Say we'll cover the problem, why it qualifies as an agent, a working prototype, "
         "governance, and a concrete 2-week ask.")

# =========================================================== 2. Problem
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Trusting a published result costs days of expert time")
steps = [("Read methods", "Parameters often\nunder-specified"), ("Find dataset", "Hunt accession\nin GEO / SRA"),
         ("Rebuild pipeline", "Guess genome build,\ntools, thresholds"), ("Re-run analysis", "Hours of compute\n+ debugging"),
         ("Compare", "Does it match?\nWhy not?")]
for i, (h, d) in enumerate(steps):
    x = 0.6 + i * 1.62
    box(s, x, 2.0, 1.45, 2.3, fill=SOFT)
    circle_num(s, x + 0.47, 2.2, 0.5, str(i + 1))
    text(s, x + 0.08, 2.85, 1.3, 0.55, h, size=14, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + 0.08, 3.4, 1.3, 0.8, d, size=11, color=GREY, align=PP_ALIGN.CENTER)
    if i < 4:
        arrow(s, x + 1.47, 3.15, x + 1.6, 3.15, color=TEAL)
text(s, 0.6, 4.6, 8, 0.4, "Today: manual, by a bioinformatician, per paper", size=14, color=GREY, italic=True)
text(s, 0.6, 5.1, 7.9, 1.8, [
    [("Cost of inaction: ", {"bold": True}), ("skilled time spent on mechanical reproduction, "
                                             "not interpretation. It scales linearly with literature volume.", {})],
    [("Variance: ", {"bold": True}), ("quality depends on how well each paper documents its methods.", {})]],
     size=15, space_after=8)
box(s, 9.0, 1.9, 3.7, 4.9, fill=INK)
text(s, 9.3, 2.15, 3.2, 0.4, "WITH THE AGENT", size=12, bold=True, color=AMBER)
text(s, 9.3, 2.6, 3.3, 0.8, "Days → minutes", size=28, bold=True, font=HEAD, color=WHITE)
text(s, 9.3, 3.45, 3.1, 0.8, "≈75 seconds end-to-end on Amazon Bedrock, including the DESeq2 re-analysis",
     size=12, color="B9D3D6")
text(s, 9.3, 4.6, 3.2, 0.9, "12 / 12", size=34, bold=True, font=HEAD, color=WHITE)
text(s, 9.3, 5.45, 3.1, 0.9, "published gene claims independently confirmed on the demo paper", size=12,
     color="B9D3D6")
notes(s, "Walk the 5 manual steps. Ask the team LIVE: how many papers per month do we validate? "
         "That number drives the ROI case (template section 1, 'TO DISCUSS LIVE').")

# =========================================================== 3. Why an agent
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "It passes all five agent-candidate checks", "Assessment checklist, section 3")
qs = [("Multi-step, multi-tool?", "Read paper → extract IDs → pull data → run DESeq2 → compare"),
      ("Needs judgment?", "Map the paper's comparison onto GEO samples; choose a paired design"),
      ("Repeatable, clear goal state?", "Verdict: reproduced / partially / not reproduced"),
      ("Autonomy OK with oversight?", "Public data only; human gates at download and sign-off"),
      ("Data and tools reachable by API?", "Europe PMC, NCBI GEO: public, documented, no key needed")]
for i, (q, a) in enumerate(qs):
    y = 1.95 + i * 0.95
    circle_num(s, 0.6, y, 0.6, "✓", fill=TEAL, size=20)
    text(s, 1.4, y - 0.02, 4.3, 0.65, [[(f"Q{i + 1}  ", {"color": TEAL}), (q, {})]], size=17, bold=True,
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, 5.6, y - 0.02, 4.0, 0.65, a, size=13, color=GREY, anchor=MSO_ANCHOR.MIDDLE)
box(s, 9.95, 1.95, 2.8, 4.45, fill=MINT)
text(s, 10.2, 2.2, 2.4, 0.4, "RECOMMENDED TIER", size=12, bold=True, color=TEAL)
text(s, 10.2, 2.65, 2.4, 1.0, "Single agent + tools", size=26, bold=True, font=HEAD)
text(s, 10.2, 3.85, 2.35, 2.4, "Simplest tier that solves it. No sub-agents and no long-term memory; "
     "each paper is a self-contained run. The tool contracts are built so we can scale later.",
     size=12, color=GREY)
notes(s, "5 of 5 YES = strong candidate. Emphasise that we deliberately chose the simplest tier (the guide's advice).")

# =========================================================== 4. Architecture
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Architecture: LLM decides, code calculates, humans approve", size=30)


def node(x, y, w, h, head, sub, fill=SOFT, head_color=INK, line=None):
    b = box(s, x, y, w, h, fill=fill, line=line)
    text(b, content=[[(head, {"bold": True, "size": 13, "color": head_color})],
                     [(sub, {"size": 10.5, "color": GREY})]], align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE, margin=0.05)
    return b


node(0.5, 3.35, 1.7, 1.0, "Scientist", "PMID / DOI", fill="FCEFD9")
box(s, 2.55, 2.35, 3.0, 3.1, fill=None, line=TEAL)
text(s, 2.7, 2.42, 2.8, 0.3, "Reproduction agent loop", size=11, bold=True, color=TEAL)
node(2.8, 2.8, 2.5, 1.05, "LLM planner", "reason → act → observe\n(Bedrock · Nova Pro, swappable)", fill="DCEBFB")
node(2.8, 4.1, 2.5, 1.1, "Guardrails", "step limit · blinding rule\nschema-checked tools", fill="FBE3DF")
tools = [("resolve_paper · get_paper_sections", "Europe PMC full text"),
         ("register_published_claims", "blinded pre-registration"),
         ("get_geo_series · download_counts", "NCBI GEO  (human-gated)"),
         ("run_differential_expression", "PyDESeq2, paired design"),
         ("compare_with_published", "deterministic verdict")]
for i, (h, d) in enumerate(tools):
    y = 1.45 + i * 0.88
    node(6.25, y, 3.2, 0.74, h, d)
    arrow(s, 5.55, 3.9, 6.23, y + 0.37, color="9FB5B9", width=1)
node(10.05, 3.21, 1.35, 0.8, "Human", "approves download", fill="FCEFD9")
arrow(s, 9.47, 3.58, 10.03, 3.58, color=AMBER, dashed=True)
arrow(s, 2.22, 3.85, 2.78, 3.35, color=TEAL)
node(2.8, 5.95, 2.5, 0.85, "Critic model", "LLM-as-judge QA", fill="ECE4FA")
arrow(s, 4.05, 5.47, 4.05, 5.93, color=PURPLE)
node(6.25, 6.05, 3.2, 0.75, "Report + provenance", "genome build · params · versions")
arrow(s, 5.32, 6.4, 6.23, 6.4, color=GREY)
node(10.05, 6.05, 1.35, 0.75, "Human", "sign-off", fill="FCEFD9")
arrow(s, 9.47, 6.42, 10.03, 6.42, color=AMBER)
cyl = box(s, 11.7, 4.9, 1.2, 1.2, fill=MINT, shape=MSO_SHAPE.CAN)
text(cyl, content=[[("Audit trail", {"bold": True, "size": 11})], [("trace.jsonl", {"size": 9, "color": GREY})]],
     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0.02)
text(s, 11.45, 6.2, 1.7, 0.6, "every thought, call,\napproval, result", size=9.5, color=GREY, align=PP_ALIGN.CENTER)
notes(s, "Key message: the LLM makes the judgment calls (which samples, which contrast, which claims). "
         "Every number is computed by deterministic code. Two human gates. An independent critic "
         "checks the report against raw tool outputs. Every step is logged. The tool definitions are "
         "plain JSON schemas, so they map 1:1 to MCP servers or Copilot Studio actions.")

# =========================================================== 5. Demo flow
s = prs.slides.add_slide(BLANK)
bg(s, SOFT)
title(s, "Live demo: a real published RNA-seq study",
      "Himes et al. 2014, PLoS One · dexamethasone in airway smooth muscle · PMID 24926665 · GEO GSE52778 "
      "· 16 samples, 4 donors × 4 treatments")
flow = [("Read", "Resolves paper, pulls\nMethods + Results"),
        ("Pre-register", "Locks 12 gene claims\nbefore seeing data"),
        ("Map samples", "Picks Untreated vs Dex,\ndrops Albuterol arms"),
        ("Human gate", "Asks approval to\ndownload counts"),
        ("Re-analyse", "DESeq2, paired by\ndonor, GRCh38"),
        ("Score", "Code computes the\nverdict, not the LLM"),
        ("Explain", "Classifies divergences:\ntechnical vs genuine"),
        ("QA + sign-off", "Critic review, then\nhuman approves")]
for i, (h, d) in enumerate(flow):
    col, row = i % 4, i // 4
    x, y = 0.6 + col * 3.1, 2.1 + row * 2.45
    fill = "FCEFD9" if h in ("Human gate", "QA + sign-off") else WHITE
    box(s, x, y, 2.85, 2.1, fill=fill)
    circle_num(s, x + 0.25, y + 0.25, 0.55, str(i + 1), fill=AMBER if fill != WHITE else TEAL)
    text(s, x + 0.95, y + 0.3, 1.8, 0.45, h, size=17, bold=True, font=HEAD)
    text(s, x + 0.25, y + 1.0, 2.45, 0.95, d, size=13, color=GREY)
notes(s, "DEMO SCRIPT: streamlit run app.py. 'Live run' with PMID 24926665 takes about 75 s on Bedrock. "
         "Backup: sidebar 'Replay a recorded run' → DEMO-himes2014-bedrock-nova (no network needed). "
         "Point out step 3: the agent chose a PAIRED design on its own because the same 4 donors appear in both arms. "
         "Optional: turn off 'Approve external data download' to show the agent stopping at the human gate. "
         "Finish on the Results tab: volcano plot, then type your name and click Approve.")

# =========================================================== 6. Results
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Result: reproduced, and the agent explains the gap")
stats = [(cmp_["verdict"], "deterministic verdict", TEAL), (cmp_["claims_confirmed"], "pre-registered claims confirmed", INK),
         (f"{cmp_['our_de_gene_count_at_reported_fdr']:,} vs {cmp_['reported_de_gene_count']}",
          "DE genes at FDR 0.05: ours vs paper", RED)]
for i, (v, l, c) in enumerate(stats):
    y = 1.75 + i * 1.45
    text(s, 0.6, y, 5.0, 0.8, v, size=36, bold=True, font=HEAD, color=c)
    text(s, 0.6, y + 0.75, 5.0, 0.4, l, size=13, color=GREY)
box(s, 0.6, 6.15, 5.2, 0.95, fill=MINT)
text(s, 0.8, 6.2, 4.9, 0.85, [[("Why the gap? TECHNICAL, not a discrepancy. ", {"bold": True}),
                              ("Paper: TopHat/Cuffdiff on hg19. Ours: HISAT2 counts on GRCh38 + "
                               "paired DESeq2, which has more power. Effect sizes agree closely.", {})]],
     size=11.5, anchor=MSO_ANCHOR.MIDDLE)
cd = CategoryChartData()
cd.categories = [g["gene"] for g in genes]
cd.add_series("log2 fold change (Dex vs untreated)", [g["log2FC"] for g in genes])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(6.3), Inches(1.6), Inches(6.5), Inches(5.5), cd)
ch = gf.chart
ch.has_legend = False
ch.has_title = True
ch.chart_title.text_frame.text = "Re-computed log2 fold change for the 12 genes the paper reported"
tp = ch.chart_title.text_frame.paragraphs[0].runs[0].font
tp.size, tp.bold, tp.color.rgb, tp.name = Pt(13), True, rgb(INK), BODY
plot = ch.plots[0]
plot.gap_width = 45
plot.series[0].invert_if_negative = False
plot.has_data_labels = True
dl = plot.data_labels
dl.number_format, dl.number_format_is_linked = '0.0;-0.0', False
dl.position = XL_LABEL_POSITION.OUTSIDE_END
dl.font.size, dl.font.color.rgb = Pt(10), rgb(GREY)
for i, g in enumerate(genes):
    pt = plot.series[0].points[i]
    pt.format.fill.solid()
    pt.format.fill.fore_color.rgb = rgb(TEAL if g["log2FC"] > 0 else RED)
for dpt in plot.series[0]._element.findall(qn("c:dPt")):  # keep negative bars filled
    idx = dpt.find(qn("c:idx"))
    inv = etree.Element(qn("c:invertIfNegative"), val="0")
    idx.addnext(inv)
ch.category_axis.tick_labels.font.size = Pt(10.5)
ch.category_axis.format.line.color.rgb = rgb("C9D3D5")
ch.value_axis.tick_labels.font.size = Pt(10)
ch.value_axis.tick_labels.font.color.rgb = rgb(GREY)
ch.value_axis.major_gridlines.format.line.color.rgb = rgb("E6ECED")
ch.value_axis.format.line.fill.background()
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = -4, 6
notes(s, "All 12 claims match in direction and are significant (padj far below 0.05). "
         f"The agent tested {de['genes_tested']:,} genes. The count gap (4,552 vs 316) is the teachable moment: the agent "
         "correctly calls it a technical divergence (different genome build, aligner, quantifier and DE method), "
         "which is exactly the 'genome build mismatch vs genuine discrepancy' distinction our template asks for.")

# =========================================================== 7. Governance
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Governance is built into the design", "Maps to the risk-mitigation checklist, section 7")
cards = [("Code computes, LLM judges", "The model never produces a statistic. DESeq2 and a fixed rule decide the verdict.", TEAL),
         ("Blinded pre-registration", "Claims are locked before analysis. Genes not found in the paper text are rejected.", TEAL),
         ("Human-in-the-loop", "Approval before external downloads. Sign-off before anything is cited.", AMBER),
         ("Independent critic", "A second model checks every number in the report against raw tool outputs.", PURPLE),
         ("Full provenance", "Genome build, pipeline, design, contrast, samples, model and software versions.", TEAL),
         ("Append-only audit trail", "Every thought, tool call, approval and result is logged per run.", TEAL)]
for i, (h, d, c) in enumerate(cards):
    col, row = i % 3, i // 3
    x, y = 0.6 + col * 4.1, 1.95 + row * 2.05
    box(s, x, y, 3.85, 1.8, fill=SOFT)
    box(s, x + 0.25, y + 0.28, 0.42, 0.42, fill=c, shape=MSO_SHAPE.OVAL)
    text(s, x + 0.85, y + 0.22, 2.9, 0.55, h, size=15, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.25, y + 0.85, 3.4, 0.9, d, size=12, color=GREY)
box(s, 0.6, 6.15, 12.1, 0.85, fill="FCEFD9")
text(s, 0.85, 6.15, 11.7, 0.85, [[("Pilot caveat: ", {"bold": True}),
                                 ("the prototype runs on a personal AWS account (Amazon Bedrock, Nova Pro; Bedrock "
                                  "doesn't train on prompts). It sees public papers and public GEO data only. Before any "
                                  "internal data, move to an approved enterprise account and check the AI Registry decision tree.", {})]],
     size=12.5, anchor=MSO_ANCHOR.MIDDLE)
notes(s, "Be upfront about the personal-account caveat; it builds trust. Section 7 items this already covers: "
         "output validation, source traceability, scope limits, human approval, decision logging.")

# =========================================================== 8. Tech stack
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Tech stack: pilot today, production path tomorrow")
rows = [("Layer", "Pilot (built)", "Production option"),
        ("LLM", "Amazon Bedrock (Nova Pro); Gemini as fallback", "Enterprise Bedrock (Claude), Copilot Studio or Cortex"),
        ("Agent runtime", "Custom Python loop, provider-swappable", "Bedrock AgentCore Runtime, or Copilot Studio"),
        ("Tools", "Python registry with JSON schemas", "Same contracts as MCP tools (AgentCore Gateway)"),
        ("Literature", "Europe PMC REST (full text)", "+ internal library / licensed journals"),
        ("Data", "NCBI GEO reprocessed counts", "nf-core/rnaseq from raw FASTQ (any build)"),
        ("Statistics", "PyDESeq2 (paired designs)", "+ Scanpy for single-cell, limma for arrays"),
        ("UI + approvals", "Streamlit, sign-off button", "Teams adaptive cards, SharePoint reports"),
        ("Audit", "trace.jsonl per run", "AgentCore Observability, AI Registry evidence")]
tbl = s.shapes.add_table(len(rows), 3, Inches(0.6), Inches(1.6), Inches(12.1), Inches(5.3)).table
for j, wdt in enumerate((2.3, 4.6, 5.2)):
    tbl.columns[j].width = Inches(wdt)
for i, r in enumerate(rows):
    for j, v in enumerate(r):
        c = tbl.cell(i, j)
        c.fill.solid()
        c.fill.fore_color.rgb = rgb(INK if i == 0 else (SOFT if i % 2 else WHITE))
        c.margin_left = c.margin_right = Inches(0.12)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        text(c, content=v, size=13 if i else 14, bold=(i == 0 or j == 0),
             color=WHITE if i == 0 else (TEAL if j == 0 else INK))
notes(s, "Everything in the pilot column exists and runs today, with zero infrastructure spend. The right-hand column is "
         "the decision for the team: pilot fast (Python or Claude.ai) vs go straight to Copilot Studio.")

# =========================================================== 9. Roadmap
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Roadmap: prove it on our backlog, then scale")
phases = [("Weeks 0–2", "Scope", "Run 3–5 real backlog papers. Score feasibility. Registry check."),
          ("Days 15–45", "Build substrate", "Host on AgentCore, MCP tools, FASTQ path, arrays and scRNA-seq."),
          ("Days 45–75", "Shadow mode", "Agent runs alongside analysts. Measure agreement and time saved."),
          ("Days 75–90", "Controlled go-live", "Teams approvals, owners assigned, 30/60/90 KPI review.")]
for i, (when, what, d) in enumerate(phases):
    x = 0.6 + i * 3.1
    box(s, x, 1.85, 2.85, 2.6, fill=MINT if i else INK)
    text(s, x + 0.25, 2.05, 2.4, 0.35, when, size=12, bold=True, color=AMBER if i == 0 else TEAL)
    text(s, x + 0.25, 2.45, 2.4, 0.5, what, size=20, bold=True, font=HEAD, color=WHITE if i == 0 else INK)
    text(s, x + 0.25, 3.1, 2.4, 1.3, d, size=12.5, color="CFE3E5" if i == 0 else GREY)
    if i < 3:
        arrow(s, x + 2.87, 3.15, x + 3.08, 3.15, color=TEAL, width=2)
text(s, 0.6, 4.8, 6, 0.45, "Where the agent pattern can go next", size=18, bold=True, font=HEAD)
ideas = [("Batch mode", "Validate every paper a team cites this quarter"),
         ("Literature watch", "Scheduled runs on new papers for our targets, posted to Teams"),
         ("Multi-agent", "Separate literature, data and stats agents once volume justifies it"),
         ("Internal data", "Same loop checks internal studies against public baselines")]
for i, (h, d) in enumerate(ideas):
    x = 0.6 + i * 3.1
    text(s, x, 5.35, 2.85, 1.5, [[(h, {"bold": True, "color": TEAL, "size": 14})], [(d, {"size": 12, "color": GREY})]],
         space_after=4)
notes(s, "Mirrors the 90-day structure in the template (scope → substrate → shadow → go-live). "
         "The 'next' ideas show the reusable pattern without over-committing now.")

# =========================================================== 10. Ask
s = prs.slides.add_slide(BLANK)
bg(s, INK)
text(s, 0.8, 0.8, 11, 0.5, "THE ASK", size=14, bold=True, color=AMBER)
text(s, 0.8, 1.3, 11.5, 1.6, "2 weeks. One real paper from our backlog. No infrastructure spend.",
     size=36, bold=True, font=HEAD, color=WHITE)
text(s, 0.8, 3.1, 6, 0.4, "Decide together today:", size=16, bold=True, color="CFE3E5")
asks = ["Papers validated per month (ROI baseline)", "Feasibility scores: fill every cell of the section 4 table",
        "Platform: Python + enterprise LLM, Claude.ai, or Copilot Studio?", "Which 3–5 backlog papers to test first",
        "Owner for the AI Registry check and version-drift monitoring"]
for i, a in enumerate(asks):
    y = 3.65 + i * 0.62
    circle_num(s, 0.8, y, 0.42, str(i + 1), fill=AMBER, color=INK, size=13)
    text(s, 1.45, y - 0.04, 10.5, 0.5, a, size=16, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
notes(s, "Close on the decisions. Leave no feasibility cell blank. Offer to run one of their own papers "
         "through the agent live if time allows.")

out = HERE / "Lit2Analysis_Agent_Pilot.pptx"
prs.save(out)
print(out)
