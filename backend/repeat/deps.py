"""Process-wide dependencies handed to agent nodes. Set once at app startup."""

from __future__ import annotations

from dataclasses import dataclass

from .bus import EventBus
from .config import Settings
from .integrations.base import Integrations
from .llm.base import LLMProvider
from .store import Store


@dataclass
class Deps:
    settings: Settings
    store: Store
    bus: EventBus
    integrations: Integrations
    llm: LLMProvider


_deps: Deps | None = None


def set_deps(d: Deps) -> None:
    global _deps
    _deps = d


def get_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("Deps not initialised; app startup did not run")
    return _deps
