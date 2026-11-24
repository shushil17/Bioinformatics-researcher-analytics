"""Central settings. Everything is overridable via .env so the same code can
move from a free-tier pilot to an enterprise endpoint without edits."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()   # "gemini" | "bedrock"

# Amazon Bedrock (Converse API). Auth: AWS_BEARER_TOKEN_BEDROCK or the standard AWS credential chain.
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "us.amazon.nova-pro-v1:0")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
# free tier often returns 503 "high demand": fail over down this list
FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-3-flash-preview").split(",") if m.strip()]
CRITIC_MODEL = os.getenv("GEMINI_CRITIC_MODEL", MODEL)
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "14"))

ACTIVE_MODEL = BEDROCK_MODEL if LLM_PROVIDER == "bedrock" else MODEL   # for display / provenance

DATA_DIR = ROOT / "data"      # cached downloads (GEO matrices, paper XML)
RUNS_DIR = ROOT / "runs"      # one folder per run: trace, results, report
DATA_DIR.mkdir(exist_ok=True)
RUNS_DIR.mkdir(exist_ok=True)

HTTP_TIMEOUT = 60
USER_AGENT = "lit2analysis-pilot/0.1 (public-data reproduction agent)"
