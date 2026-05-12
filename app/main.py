from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import get_settings
from app.content_registry import registry as content_registry_module
from app.store import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db.run_migrations(settings.database_url)
    await db.init_pool(settings.database_url)
    content_registry_module.init_registry(Path(settings.content_dir))
    yield
    await db.close_pool()


app = FastAPI(title="AI Tutor", lifespan=lifespan)

from app.api import content as content_router  # noqa: E402
from app.api import learners as learners_router  # noqa: E402
from app.api import sessions as sessions_router  # noqa: E402
from app.api import tutors as tutors_router  # noqa: E402

app.include_router(learners_router.router)
app.include_router(sessions_router.router)
app.include_router(content_router.router)
app.include_router(tutors_router.router)
