"""Tiny tool registry: each tool = python function + JSON schema + policy flags.

Keeping schemas explicit (instead of SDK auto-inference) makes the tool contract
portable: the same definitions map 1:1 onto MCP tools, Copilot Studio actions,
or Anthropic/OpenAI tool-use formats.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class RunContext:
    """Per-run state shared by tools (paths, intermediate results)."""
    run_id: str
    run_dir: Path
    state: dict = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]
    requires_approval: bool = False   # human-in-the-loop gate before execution


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: list[str] | None = None,
         requires_approval: bool = False):
    def wrap(fn):
        TOOLS[name] = Tool(
            name=name,
            description=description,
            parameters={"type": "object", "properties": properties, "required": required or []},
            fn=fn,
            requires_approval=requires_approval,
        )
        return fn
    return wrap
