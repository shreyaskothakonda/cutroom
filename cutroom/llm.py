"""LLM backends for the planning agents. The tools never call these.

  claude-cli  default. Runs `claude -p` with no tools, using the local login.
  anthropic   the Messages API, needs ANTHROPIC_API_KEY.
  manual      writes the prompt to a file and waits for you (or another agent)
              to write the answer file next to it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_MODEL = os.environ.get("CUTROOM_MODEL", "sonnet")


class LLMError(RuntimeError):
    pass


def _claude_cli(system: str, prompt: str, model: str) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise LLMError("The claude CLI is not on PATH. Use --llm anthropic or --llm manual.")
    p = subprocess.run(
        [exe, "-p", "--model", model, "--tools", "", "--no-session-persistence",
         "--strict-mcp-config", "--system-prompt", system, "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=600,
    )
    if p.returncode != 0:
        why = (p.stderr.strip() or p.stdout.strip())[:400]
        hint = " Run `claude` once and log in again." if "authenticate" in why.lower() else ""
        raise LLMError(f"claude -p failed: {why}.{hint}")
    return p.stdout


def _anthropic(system: str, prompt: str, model: str) -> str:
    import anthropic

    ids = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5", "haiku": "claude-haiku-5-5"}
    msg = anthropic.Anthropic().messages.create(
        model=ids.get(model, model), max_tokens=8000, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def _manual(system: str, prompt: str, model: str, workdir: Path, name: str) -> str:
    q = workdir / f"{name}.prompt.md"
    a = workdir / f"{name}.answer.json"
    q.write_text(f"# System\n\n{system}\n\n# Prompt\n\n{prompt}\n\nWrite only JSON to {a.name}.\n")
    print(f"  waiting for {a} (prompt in {q.name})")
    while not a.exists():
        time.sleep(2)
    return a.read_text()


def extract_json(text: str):
    """Pull the first JSON object or array out of a model reply."""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError("No JSON in model reply")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise LLMError("Unbalanced JSON in model reply")


class LLM:
    def __init__(self, backend: str = "claude-cli", model: str = DEFAULT_MODEL, workdir: Path | None = None):
        self.backend, self.model, self.workdir = backend, model, workdir

    def json(self, name: str, system: str, prompt: str, retries: int = 1):
        """Ask for JSON. Retries once with the parse error if the reply is malformed."""
        last = None
        for _ in range(retries + 1):
            ask = prompt if last is None else f"{prompt}\n\nYour last reply was not valid JSON ({last}). Reply with JSON only."
            if self.backend == "claude-cli":
                text = _claude_cli(system, ask, self.model)
            elif self.backend == "anthropic":
                text = _anthropic(system, ask, self.model)
            elif self.backend == "manual":
                text = _manual(system, ask, self.model, self.workdir, name)
            else:
                raise LLMError(f"Unknown LLM backend {self.backend}")
            if self.workdir:
                (self.workdir / f"{name}.reply.txt").write_text(text)
            try:
                return extract_json(text)
            except (LLMError, json.JSONDecodeError) as e:
                last = str(e)
        raise LLMError(f"{name}: no valid JSON after {retries + 1} tries ({last})")
