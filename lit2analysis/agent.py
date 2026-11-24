"""Model-agnostic agent loop (reason -> act -> observe) with governance hooks.

Hooks that matter for a regulated environment:
  * on_event  - every thought / tool call / result is streamed and written to an
                append-only audit trail (runs/<id>/trace.jsonl)
  * approver  - human-in-the-loop gate for tools flagged requires_approval
  * max_steps - hard ceiling on autonomy

The LLM sits behind a small backend interface (GeminiBackend, BedrockBackend), selected
by LLM_PROVIDER in .env. The loop, tools and governance hooks don't change per provider.
"""
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import config
from .tools import TOOLS, RunContext, Tool

Event = dict
Approver = Callable[[str, dict], bool]
OnRetry = Callable[[str, str, int], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jsonable(obj, limit: int = 20000) -> str:
    s = json.dumps(obj, default=str, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + '..."[truncated]"'


def _payload(result, limit: int = 20000):
    """Tool result as JSON-safe data, truncated for the model if very large."""
    raw = json.dumps(result, default=str, ensure_ascii=False)
    return json.loads(raw) if len(raw) <= limit else raw[:limit] + " [truncated]"


@dataclass
class Call:
    id: str
    name: str
    args: dict


@dataclass
class Turn:
    thoughts: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    text: str = ""


# ============================================================ backends
class GeminiBackend:
    def __init__(self, system_prompt: str, tools: list[Tool], on_retry: OnRetry):
        from google import genai
        from google.genai import types
        self.types, self.on_retry = types, on_retry
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.contents = []
        self.gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t.name, description=t.description,
                                          parameters_json_schema=t.parameters) for t in tools])],
            thinking_config=types.ThinkingConfig(include_thoughts=True),
        )

    def start(self, task: str) -> None:
        self.contents = [self.types.Content(role="user", parts=[self.types.Part(text=task)])]

    def step(self) -> Turn:
        resp = _gemini_failover(
            lambda m: self.client.models.generate_content(model=m, contents=self.contents,
                                                          config=self.gen_config),
            config.MODEL, self.on_retry)
        cand = resp.candidates[0]
        self.contents.append(cand.content)  # keeps thought signatures intact
        turn, text = Turn(), []
        for part in cand.content.parts or []:
            if part.thought and part.text:
                turn.thoughts.append(part.text)
            elif part.function_call:
                fc = part.function_call
                turn.calls.append(Call(fc.id, fc.name, dict(fc.args or {})))
            elif part.text:
                text.append(part.text)
        turn.text = "\n".join(text).strip()
        return turn

    def add_results(self, results: list[tuple[Call, object]]) -> None:
        t = self.types
        self.contents.append(t.Content(role="user", parts=[
            t.Part(function_response=t.FunctionResponse(id=c.id, name=c.name,
                                                        response={"result": _payload(r)}))
            for c, r in results]))


class BedrockBackend:
    """Amazon Bedrock Converse API: one request shape for Nova, Claude, Llama, etc."""

    def __init__(self, system_prompt: str, tools: list[Tool], on_retry: OnRetry):
        import boto3
        from botocore.config import Config
        self.client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION, config=Config(
            retries={"max_attempts": 8, "mode": "adaptive"}, read_timeout=300))
        self.system = [{"text": system_prompt}]
        self.tool_config = {"tools": [{"toolSpec": {
            "name": t.name, "description": t.description, "inputSchema": {"json": t.parameters}}}
            for t in tools]}
        self.messages: list[dict] = []
        self.on_retry = on_retry

    def start(self, task: str) -> None:
        self.messages = [{"role": "user", "content": [{"text": task}]}]

    def step(self) -> Turn:
        resp = self.client.converse(modelId=config.BEDROCK_MODEL, system=self.system,
                                    messages=self.messages, toolConfig=self.tool_config,
                                    inferenceConfig={"maxTokens": 4096, "temperature": 0.2})
        msg = resp["output"]["message"]
        self.messages.append(msg)
        turn, text = Turn(), []
        for block in msg.get("content", []):
            if "toolUse" in block:
                tu = block["toolUse"]
                turn.calls.append(Call(tu["toolUseId"], tu["name"], tu.get("input") or {}))
            elif "reasoningContent" in block:
                turn.thoughts.append(block["reasoningContent"].get("reasoningText", {}).get("text", ""))
            elif "text" in block:
                text.append(block["text"])
        joined = "\n".join(text).strip()
        # Nova writes its reasoning inline as <thinking>...</thinking>; surface it as a thought
        turn.thoughts += [t.strip() for t in re.findall(r"<thinking>(.*?)</thinking>", joined, re.S)]
        joined = re.sub(r"<thinking>.*?</thinking>", "", joined, flags=re.S).strip()
        if turn.calls and joined:
            turn.thoughts.append(joined)   # narration before a tool call
        else:
            turn.text = joined
        return turn

    def add_results(self, results: list[tuple[Call, object]]) -> None:
        content = []
        for c, r in results:
            p = _payload(r)
            body = [{"json": {"result": p}}] if not isinstance(p, str) else [{"text": p}]
            block = {"toolUseId": c.id, "content": body}
            if isinstance(r, dict) and "error" in r:
                block["status"] = "error"
            content.append({"toolResult": block})
        self.messages.append({"role": "user", "content": content})


def make_backend(system_prompt: str, tools: list[Tool], on_retry: OnRetry):
    cls = BedrockBackend if config.LLM_PROVIDER == "bedrock" else GeminiBackend
    return cls(system_prompt, tools, on_retry)


# ============================================================ agent loop
class Agent:
    def __init__(self, ctx: RunContext, system_prompt: str, tool_names: list[str] | None = None,
                 on_event: Callable[[Event], None] | None = None,
                 approver: Approver | None = None, max_steps: int = config.MAX_AGENT_STEPS):
        self.ctx, self.max_steps = ctx, max_steps
        self.tools = {n: TOOLS[n] for n in (tool_names or TOOLS)}
        self.on_event = on_event or (lambda e: None)
        self.approver = approver or (lambda name, args: True)
        self.trace_path = ctx.run_dir / "trace.jsonl"
        self.llm = make_backend(system_prompt, list(self.tools.values()),
                                lambda m, why, wait: self.emit("retry", model=m, reason=why, wait_s=wait))

    # ---- audit ----------------------------------------------------------
    def emit(self, type_: str, **data) -> None:
        event = {"ts": _now(), "run_id": self.ctx.run_id, "type": type_, **data}
        with self.trace_path.open("a", encoding="utf-8") as f:
            f.write(_jsonable(event, limit=200000) + "\n")
        self.on_event(event)

    # ---- main loop -------------------------------------------------------
    def run(self, task: str) -> str:
        self.llm.start(task)
        self.emit("task", text=task, model=config.ACTIVE_MODEL, provider=config.LLM_PROVIDER,
                  tools=list(self.tools))

        for step in range(1, self.max_steps + 1):
            turn = self.llm.step()
            for t in turn.thoughts:
                if t:
                    self.emit("thought", step=step, text=t)

            if not turn.calls:
                self.emit("final", step=step, text=turn.text)
                return turn.text

            results = []
            for call in turn.calls:
                self.emit("tool_call", step=step, tool=call.name, args=call.args)
                result = self._execute(call.name, call.args)
                self.emit("tool_result", step=step, tool=call.name, result=result)
                results.append((call, result))
            self.llm.add_results(results)

        msg = f"Stopped: reached max_steps={self.max_steps} without a final answer."
        self.emit("final", step=self.max_steps, text=msg)
        return msg

    def _execute(self, name: str, args: dict):
        t = self.tools.get(name)
        if t is None:
            return {"error": f"Unknown tool {name}"}
        if t.requires_approval:
            ok = self.approver(name, args)
            self.emit("approval", tool=name, args=args, approved=ok)
            if not ok:
                return {"error": "Human reviewer declined this action. Stop and report."}
        try:
            return t.fn(self.ctx, **args)
        except Exception as e:  # tool errors go back to the model so it can adapt
            return {"error": f"{type(e).__name__}: {e}"}


# ============================================================ helpers
def _gemini_failover(call, primary: str, on_retry: OnRetry = lambda m, why, wait: None):
    """Free-tier Gemini: try the primary model, then each fallback; cycle with backoff."""
    from google.genai import errors
    models = [primary] + [m for m in config.FALLBACK_MODELS if m != primary]
    last = None
    for round_ in range(4):
        for m in models:
            try:
                return call(m)
            except errors.APIError as e:
                if e.code not in (429, 500, 503, 404):
                    raise
                last = e
                on_retry(m, f"API {e.code}", 0)
        wait = 10 * (round_ + 1)
        on_retry("all", "all models busy", wait)
        time.sleep(wait)
    raise last


def complete(prompt: str, system: str) -> str:
    """Single tool-less LLM call (used by the critic), on the configured provider."""
    if config.LLM_PROVIDER == "bedrock":
        import boto3
        client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)
        r = client.converse(modelId=config.BEDROCK_MODEL, system=[{"text": system}],
                            messages=[{"role": "user", "content": [{"text": prompt}]}],
                            inferenceConfig={"maxTokens": 2048, "temperature": 0})
        return "".join(b.get("text", "") for b in r["output"]["message"]["content"])

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    cfg = types.GenerateContentConfig(system_instruction=system, temperature=0)
    r = _gemini_failover(lambda m: client.models.generate_content(model=m, contents=prompt, config=cfg),
                         config.CRITIC_MODEL)
    return r.text or ""
