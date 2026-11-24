"""CLI entry point.

    python run_agent.py 24926665            # PMID, PMCID, or DOI
    python run_agent.py 24926665 --yes      # auto-approve downloads (unattended)
"""
import argparse
import json
import sys

from lit2analysis import pipeline

COLORS = {"thought": "\033[90m", "tool_call": "\033[36m", "tool_result": "\033[32m",
          "approval": "\033[33m", "final": "\033[1m", "critic": "\033[35m", "retry": "\033[31m"}


def show(e: dict) -> None:
    c, t = COLORS.get(e["type"], ""), e["type"]
    if t == "thought":
        body = e["text"][:400]
    elif t == "tool_call":
        body = f"{e['tool']}({json.dumps(e['args'])})"
    elif t == "tool_result":
        body = json.dumps(e["result"], default=str)[:300]
    elif t in ("final", "critic"):
        body = "\n" + e["text"]
    else:
        body = json.dumps({k: v for k, v in e.items() if k not in ("ts", "run_id", "type")}, default=str)[:300]
    print(f"{c}[{t}] {body}\033[0m\n", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paper", help="PMID, PMCID, or DOI")
    ap.add_argument("--yes", action="store_true", help="auto-approve gated actions")
    a = ap.parse_args()

    def approver(tool: str, args: dict) -> bool:
        if a.yes:
            return True
        return input(f"\n>>> Agent requests '{tool}' {args}. Approve? [y/N] ").strip().lower() == "y"

    ctx = pipeline.run(a.paper, on_event=show, approver=approver)
    print(f"\nReport: {ctx.run_dir / 'report.md'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
