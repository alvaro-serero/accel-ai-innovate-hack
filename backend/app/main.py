"""FastAPI entry point. Owner: Marc.

Run locally:  uvicorn backend.app.main:app --reload --port 8080   (docs at /docs)
"""
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agent.routes import router as agent_router
from backend.app.config import settings
from backend.eval.routes import router as eval_router
from backend.events.routes import router as events_router
from backend.watcher.routes import register_jobs
from backend.watcher.routes import router as watcher_router

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.enable_scheduler:
        register_jobs(scheduler)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="FirstIn API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "scheduler": settings.enable_scheduler}


app.include_router(agent_router)
app.include_router(watcher_router)
app.include_router(events_router)
app.include_router(eval_router)
