"""Prompt registry. Every prompt is a versioned .md file in this folder.

Usage:
    system, user = render("generalize", data={...})

The user message always ends with a `DATA:` block containing JSON. The mock
provider parses that block; OpenAI reads it like any other context.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent
PROMPT_VERSION = "v1"


@lru_cache
def _load(name: str) -> str:
    path = PROMPTS_DIR / PROMPT_VERSION / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt {name!r} not found at {path}")
    return path.read_text(encoding="utf-8")


def render(name: str, data: dict) -> tuple[str, str]:
    text = _load(name)
    if "---USER---" not in text:
        raise ValueError(f"prompt {name!r} is missing the ---USER--- separator")
    system, user = text.split("---USER---", 1)
    user = user.strip() + "\n\nDATA:\n" + json.dumps(data, ensure_ascii=False, indent=2)
    return system.strip(), user
