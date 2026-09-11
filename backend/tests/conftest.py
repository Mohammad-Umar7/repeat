import os

import pytest

os.environ.setdefault("REPEAT_DEMO_MODE", "true")
os.environ.setdefault("REPEAT_LLM_PROVIDER", "mock")
os.environ.pop("OPENAI_API_KEY", None)

from repeat.bus import EventBus  # noqa: E402
from repeat.config import Settings  # noqa: E402
from repeat.deps import Deps, set_deps  # noqa: E402
from repeat.integrations import get_integrations  # noqa: E402
from repeat.llm.mock_provider import MockProvider  # noqa: E402
from repeat.store import Store  # noqa: E402


@pytest.fixture
async def deps(tmp_path):
    settings = Settings(repeat_demo_mode=True, repeat_llm_provider="mock", repeat_db_path=tmp_path / "t.db")
    store = await Store(settings.repeat_db_path).open()
    get_integrations.cache_clear()
    d = Deps(settings=settings, store=store, bus=EventBus(), integrations=get_integrations(), llm=MockProvider())
    set_deps(d)
    yield d
    await store.close()
