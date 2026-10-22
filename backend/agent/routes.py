"""Agent routes. Owner: Alvaro.
Thin HTTP layer: the logic lives in profile.py, qualify.py, research.py, run.py, memory.py, kit.py.
Keep paths and response models (Marc's UI depends on them).
"""
import asyncio

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from backend.agent import kit, memory, profile, run
from backend.app.db import execute
from backend.app.schemas import (
    Brief,
    FeedbackIn,
    FeedbackResult,
    Kit,
    KitRequest,
    Match,
    MatchPatch,
    RunCreate,
    RunCreated,
    RunOut,
    User,
)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/users", response_model=User)
async def create_user(
    cv: UploadFile = File(...),
    name: str = Form(""),
    email: str = Form(""),
    city: str = Form("Paris"),
    target_roles: str = Form(""),  # comma-separated
    target_companies: str = Form(""),  # comma-separated
    start_date: str = Form(""),  # YYYY-MM-DD
):
    pdf_bytes = await cv.read()
    try:
        # Sonnet call is blocking: run it in a thread so the server stays responsive.
        user = await asyncio.to_thread(
            profile.onboard_user,
            pdf_bytes, name, email, city, target_roles, target_companies, start_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return user


@router.get("/users/{user_id}", response_model=User)
def get_user(user_id: int):
    user = profile.load_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.post("/users/{user_id}/runs", response_model=RunCreated)
def start_run(user_id: int, background_tasks: BackgroundTasks, body: RunCreate | None = None):
    if profile.load_user(user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    run_id = run.create_run(user_id, (body or RunCreate()).kind)
    background_tasks.add_task(run.execute_run, run_id, user_id)  # starts after the response is sent
    return RunCreated(run_id=run_id)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int):
    found = run.load_run(run_id)
    if found is None:
        raise HTTPException(status_code=404, detail="run not found")
    return found


@router.get("/users/{user_id}/brief", response_model=Brief)
def get_brief(user_id: int):
    return run.load_brief(user_id)


@router.post("/feedback", response_model=FeedbackResult)
def post_feedback(body: FeedbackIn):
    if profile.load_user(body.user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    return memory.handle_feedback(body.user_id, body.target_type, body.target_id, body.verdict, body.reason)


@router.post("/jobs/{job_id}/kit", response_model=Kit)
def make_kit(job_id: int, body: KitRequest):
    user = profile.load_user(body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    job = kit.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return kit.make_kit(user, job)  # saved to kits, never sent: the student sends it


@router.patch("/matches/{match_id}", response_model=Match)
def patch_match(match_id: int, body: MatchPatch):
    if not execute("update matches set status = %s where id = %s", (body.status, match_id)):
        raise HTTPException(status_code=404, detail="match not found")
    return run.load_match(match_id)
