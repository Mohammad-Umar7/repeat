"""FastAPI application. Local only: binds to 127.0.0.1 and accepts the extension origin."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..bus import EventBus
from ..config import get_settings
from ..deps import Deps, set_deps
from ..integrations import get_integrations
from ..llm import get_llm
from ..seed import seed_demo
from ..store import Store
from .routes import router
from .ws import ws_router

log = logging.getLogger("repeat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logging.basicConfig(level=s.repeat_log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store = await Store(s.repeat_db_path).open()
    deps = Deps(settings=s, store=store, bus=EventBus(), integrations=get_integrations(), llm=get_llm())
    set_deps(deps)
    if s.repeat_seed_demo and not await store.list_workflows():
        await seed_demo(wipe=False)
        log.info("seeded demo workflow")
    log.info(
        "REPEAT %s ready on http://127.0.0.1:%d  (integrations=%s, llm=%s)",
        __version__, s.repeat_port, deps.integrations.mode, deps.llm.name,
    )
    try:
        yield
    finally:
        await store.close()


def create_app() -> FastAPI:
    app = FastAPI(title="REPEAT", version=__version__, lifespan=lifespan, docs_url="/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(chrome-extension://[a-z]{32}|http://(localhost|127\.0\.0\.1)(:\d+)?)$",
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.include_router(router)
    app.include_router(ws_router)
    return app


app = create_app()
