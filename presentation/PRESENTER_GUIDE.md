# Presenter Guide: Literature-to-Analysis Agent

A talk track for the working session: which browser tabs to open, what to say at each point,
the background behind each concept, and what goes **in** and comes **out** at every step.

---

## 1. Before you start (10 minutes before)

- [ ] Generate a fresh Bedrock API key (short-term keys expire within 12 h) and paste it into `.env`
- [ ] Start the app: `venv\Scripts\streamlit run app.py`, then do one warm-up live run
- [ ] Open PowerPoint with `presentation/Lit2Analysis_Agent_Pilot.pptx` (speaker notes on)
- [ ] In Edge, create a **tab group called "Demo"** (right-click a tab → *Add tab to new group*) with the tabs below, in order
- [ ] Set Edge zoom to 125% (Ctrl + +) so the room can read it
- [ ] Close email, Teams chats and other tabs you don't want on screen

## 2. Edge tabs, in the order you'll use them

| # | Tab | URL | Why it's open |
|---|---|---|---|
| 1 | **The paper on PubMed** | https://pubmed.ncbi.nlm.nih.gov/24926665/ | Starting point: "this is the paper we want to trust" |
| 2 | **Full text on PMC** | https://pmc.ncbi.nlm.nih.gov/articles/PMC4057123/ | Show the Methods section and **Table 1** (the genes the paper claims) |
| 3 | **Europe PMC API** (what the agent actually calls) | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:24926665&format=json | Show that it's a plain, free, machine-readable API with no key |
| 4 | **GEO series GSE52778** | https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE52778 | The public dataset behind the paper: 16 samples |
| 5 | **One GEO sample** | https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM1275863 | Show the metadata the agent reads (`treatment: Dexamethasone`, `cell line: N61311`) |
| 6 | **NCBI-generated counts** | https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE52778 | Scroll to *NCBI-generated data*: the ready-made count matrix on GRCh38 |
| 7 | **How NCBI processed it** | https://www.ncbi.nlm.nih.gov/geo/info/rnaseqcounts.html | Backup only, if someone asks "how were the counts made?" |
| 8 | **The demo app** | http://localhost:8501 | The live agent run, results, volcano plot, sign-off, architecture |
| 9 | **PyDESeq2 docs** (optional) | https://pydeseq2.readthedocs.io | Backup only, if a statistician asks about the method |
| 10 | **AWS Bedrock console** (optional) | https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1 | Only if asked "where does the LLM run?" **Careful: it shows your account ID and billing. Show the model catalog page only.** |
| 11 | **GitHub repo** (once created) | your repo URL | "The code is here; reusable, nothing hidden" |

**Open all NCBI tabs (1, 2, 4–7) before the meeting.** NCBI sometimes shows a "Checking your browser"
page first. Get past it once beforehand so no check appears on screen during the talk.

Tip: tabs 7, 9 and 10 are backups. Leave them at the end of the group and only open them if asked.

---

## 3. Run of show (~15–20 minutes)

| Time | Slide | Tab | What you do |
|---|---|---|---|
| 0:00 | 1 Title | – | One-line hook |
| 1:00 | 2 Problem | 1, 2 | Show the paper and Table 1: "to trust this, someone re-does it by hand" |
| 3:00 | 3 Why an agent | – | 5/5 checklist, single-agent tier |
| 4:30 | 4 Architecture | – | LLM decides, code calculates, humans approve |
| 6:00 | 5 Demo | 8 (start the run), then 3–6 while it runs | Start the live run first, then walk through the data sources while it works (~75 s) |
| 9:00 | 6 Results | 8 (Results tab) | Verdict, table, volcano, explain the 4,552 vs 316 gap, click Approve |
| 11:00 | 7 Governance | 8 (Architecture tab) | Guardrails and the pilot caveat |
| 12:30 | 8 Tech stack | – | Pilot vs production |
| 13:30 | 9 Roadmap | – | How it scales (section 6 below) |
| 15:00 | 10 Ask | – | Decisions to make together |

**Demo trick:** click **Run agent** at the start of slide 5, *then* switch to tabs 3–6 and explain the
data sources while the agent works. When you return to tab 8, the run is nearly finished.
Backup if anything fails: sidebar → **Replay a recorded run** → `DEMO-himes2014-bedrock-nova`.

---

## 4. The story, step by step: background, then what goes in and out

### Step 0: The paper (tabs 1, 2)

**Background you can say:**
- **PubMed** is the U.S. National Library of Medicine's search index of biomedical literature
  (tens of millions of citations). It holds titles and abstracts, not full text. Every paper has a
  **PMID**; ours is **24926665**.
- **PMC (PubMed Central)** is the free full-text archive. Papers in its **open-access subset** can be
  read by machines (text mining is allowed). Ours is **PMC4057123**.
- **The paper:** Himes et al., *PLoS One* 2014. Airway smooth muscle cells from **4 donors** were treated
  with **dexamethasone** (a glucocorticoid, the drug class in asthma inhalers) for 18 hours and profiled
  by **RNA-seq**. They report **316 differentially expressed genes** and identify **CRISPLD2** as a new
  glucocorticoid-responsive gene.
- **Why this paper:** it's a well-known benchmark. Its data is the "airway" dataset used in
  Bioconductor's own RNA-seq tutorials, so the audience can trust the ground truth.

**What to point at:** in tab 2, scroll to **Table 1**: the list of genes and directions the authors
claim. "This table is what we're checking."

### Step 1: Read the paper (tab 3)

**Background:** **Europe PMC** is the European mirror of PubMed and PMC, run by EMBL-EBI. It offers a
free REST API that returns the full text as structured XML, so we can pull the Methods and Results
sections cleanly. No API key is needed.

| In | Out |
|---|---|
| PMID `24926665` | Title, journal, year, abstract, PMCID `PMC4057123`, open-access = yes |
| PMCID | Methods and Results text, plus every dataset accession mentioned: `GSE13168`, `GSE34313`, `GSE52778` |

**Say:** "The paper mentions three datasets. The agent has to work out which one is the main
experiment. It picks GSE52778 and explains why."

### Step 2: Pre-register the claims (blinding)

**Background:** borrowed from clinical trials. You write down what you expect to find *before*
looking at the data, so you can't cherry-pick afterwards.

| In | Out |
|---|---|
| 12 genes with direction (e.g. `CRISPLD2:up`, `KCTD12:down`), the paper's 316 DE genes, FDR 0.05 | Accepted and rejected claims, now **locked** |

**Say:** "Code checks every gene name against the paper text. In one run the model tried to add
`C13orf15`, an outdated gene name that isn't in the paper, and it was rejected automatically. The
analysis tool refuses to run until claims are locked."

### Step 3: Find and understand the dataset (tabs 4, 5)

**Background:**
- **GEO (Gene Expression Omnibus)** is NCBI's public repository for gene-expression data. Journals
  require authors to deposit their data there.
- **GSE** = a *series* (one study). **GSM** = one *sample*. **GPL** = the *platform* (sequencer or array).
- Each sample has **characteristics**, structured labels such as `treatment: Dexamethasone` and
  `cell line: N61311`. This is what the agent reads to design the comparison.

| In | Out |
|---|---|
| `GSE52778` | 16 samples = 4 donors × 4 treatments (Untreated, Dexamethasone, Albuterol, Albuterol + Dex); count matrix available; genome build **GRCh38.p13** |

**Say (this is the judgment step):** "The paper's main comparison is dexamethasone vs untreated. The
agent picked exactly those 8 samples, dropped the albuterol arms, and noticed that the same 4 donors
appear in both groups, so it chose a **paired design** on its own. That's the kind of decision a
bioinformatician makes, and why this needs an agent rather than a script."

### Step 4: Get the data, with a human gate (tab 6)

**Background:**
- The raw sequencing reads (FASTQ files) live in **SRA**, the Sequence Read Archive. Re-aligning them
  takes hours of compute.
- **NCBI re-processes most human and mouse RNA-seq in GEO through one uniform pipeline:** reads aligned
  with **HISAT2** to the **GRCh38** genome, then counted per gene with **featureCounts**. The result is a
  **count matrix**: genes in rows, samples in columns, each cell = how many reads mapped to that gene.
- This gives the agent a consistent starting point in seconds instead of hours.

| In | Out |
|---|---|
| `GSE52778` (after a **human approves** the download) | Raw count matrix: **39,376 genes × 16 samples** (0.7 MB), plus NCBI gene symbols |

**Say:** "Before anything external is downloaded, a person has to approve it. Here I pre-approved;
I can switch that off and the agent stops at the gate."

### Step 5: Re-run the analysis

**Background:**
- **DESeq2** is the standard statistical method for RNA-seq count data. It corrects for sequencing
  depth, models each gene's variability, and tests whether expression changed between groups.
  **PyDESeq2** is its Python version.
- **log2 fold change:** +1 = doubled, +2 = 4×, −1 = halved.
- **padj (FDR):** p-value adjusted for testing ~20,000 genes at once (Benjamini–Hochberg).
  padj < 0.05 = significant.
- **Paired design (`~ pair + condition`):** compares each donor with itself, removing donor-to-donor
  baseline differences. This gives more statistical power.

| In | Out |
|---|---|
| Groups: `treatment` = Untreated vs Dexamethasone; pair by `cell line` | **21,833** genes tested (after removing near-zero genes); **4,552** significant (2,497 up, 2,055 down); full results CSV |

### Step 6: Score it (code, not the LLM)

| In | Out |
|---|---|
| The locked claims plus the DE results | Per-gene table (observed direction, log2FC, padj, status) and the verdict: **REPRODUCED, 12/12** |

**Say:** "The verdict rule is fixed code: 80% or more of claims confirmed = reproduced, 50% or more =
partial, otherwise not reproduced. The LLM never computes a number that appears in the report."

### Step 7: Explain divergences (Results tab: volcano plot)

**Background:**
- **Volcano plot:** x = fold change, y = significance. Top-left and top-right = strongly changed genes.
  Red dots = the paper's genes; all of them land in the significant zones.
- **Genome build:** the reference human genome has versions. **hg19/GRCh37** (2009) and **GRCh38**
  (2013) differ in coordinates and gene annotations, so the same reads can give slightly different
  counts. This is the most common cause of false discrepancies in re-analysis.
- **Why 4,552 vs 316?** The paper used Cuffdiff (2014-era, lower power) on hg19. We used DESeq2 with a
  paired design on GRCh38. More sensitive method, different reference, so more genes pass the cut-off.
  But **effect sizes for the top genes agree closely**. That's a TECHNICAL divergence, not a genuine
  discrepancy, which is exactly the distinction your template asks the agent to make.

### Step 8: QA and sign-off

| In | Out |
|---|---|
| The agent's report plus the raw tool outputs | Critic verdict (PASS or NEEDS REVIEW), `report.md` with provenance, `trace.jsonl` audit trail, human Approve/Reject |

**Say:** "A second model checks every number in the report against the raw outputs. If it says
NEEDS REVIEW, that's the system being cautious, which is what you want. Nothing is cited until a
person signs off."

### Where the AI runs (tab 10, only if asked)

**Background:**
- **Amazon Bedrock** is AWS's managed service for AI models. We call it through its **Converse API**.
- The model is **Amazon Nova Pro**. The code is model-agnostic: switching to Claude or Gemini is one
  setting.
- Bedrock doesn't use prompts or outputs to train models.
- **Pilot caveat:** this runs on a personal AWS account with public data only. Production would move
  to an approved enterprise account.

### What "agent" means here (for slide 4)

- An **agent** = an LLM in a loop: it **reasons** about what to do next, **acts** by calling a tool,
  **observes** the result, and repeats until done.
- A **tool** is an ordinary Python function with a description and an input schema. The model chooses
  which tool to call and with what arguments; our code executes it.
- **Guardrails:** step limit, blinding rule, human gates, deterministic scoring, independent critic,
  append-only audit trail.

---

## 5. Likely questions and short answers

| Question | Answer |
|---|---|
| What if the paper isn't open access? | The agent stops and says so. Production can add licensed or internal full text. |
| What if there's no NCBI count matrix? | It stops and recommends FASTQ re-alignment, which is on the roadmap (nf-core/rnaseq). |
| Could the LLM make up numbers? | Every number comes from code; the critic cross-checks; claims are verified against the paper text. |
| Microarray or single-cell data? | Not yet. Roadmap: limma for arrays, Scanpy for single-cell. |
| How much does a run cost? | Cents of LLM usage on Bedrock at this scale; to be measured over the pilot. |
| Does it work on other papers? | Tested on one benchmark so far. The 2-week ask is to run 3–5 papers from our backlog. |
| Why not just use ChatGPT/Claude chat? | A chatbot can't download data or run DESeq2, and gives no audit trail, blinding or sign-off. |
| Is our data safe? | The pilot uses public data only. Internal data waits for an enterprise account and an AI Registry check. |

---

## 6. Closing: how this scales

**Stage 1: Prove it (weeks 0–2)**
- Run 3–5 papers from our backlog, including at least one we *expect* not to reproduce.
- Build a small benchmark: known-good and known-bad papers with expected verdicts. This becomes our
  accuracy measure for every future change.

**Stage 2: More data types (days 15–45)**
- **Raw reads:** re-align FASTQ from SRA with **nf-core/rnaseq** (a standard Nextflow pipeline),
  run on **AWS HealthOmics** or AWS Batch. That removes the dependency on NCBI's pre-built counts and
  lets us match the paper's exact genome build.
- **Microarrays** (limma) and **single-cell** (Scanpy) as additional analysis tools. Same agent, new tools.

**Stage 3: Production hosting (days 45–75, shadow mode)**
- Host the agent on **Amazon Bedrock AgentCore Runtime** (managed, serverless), or Copilot Studio.
- Expose the tools as **MCP** servers through **AgentCore Gateway**, so other agents and teams can reuse them.
- Swap `trace.jsonl` for **AgentCore Observability** / central logging.
- Move to **Claude on an enterprise Bedrock account**.
- Run the agent alongside analysts, measuring agreement and time saved.

**Stage 4: Scale out (days 75–90 and beyond)**
- **Batch mode:** a queue of papers processed in parallel. Every paper a team cites this quarter gets
  checked automatically.
- **Literature watch:** a scheduled run on new papers about our targets, with results posted to Teams.
- **Team knowledge:** a Bedrock **Knowledge Base** of our SOPs and preferred parameters, so the agent
  follows house conventions.
- **Approvals in Teams** and reports in SharePoint.
- **Multi-agent** (separate literature, data and statistics agents) only once volume justifies it.

**Closing line:** "Today: one paper, 75 seconds, fully audited. The ask: two weeks and 3–5 of our own
papers to see if it holds up on real work."
