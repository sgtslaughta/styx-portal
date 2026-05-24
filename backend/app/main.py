from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import templates, instances


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Selkies Hub", version="0.1.0", lifespan=lifespan)
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(instances.router, prefix="/api/instances", tags=["instances"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
