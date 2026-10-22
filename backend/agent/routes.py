"""Agent routes. Owner: Alvaro.
STUBS: every route returns fixtures until the real logic replaces it. Keep paths and response models.
"""
from fastapi import APIRouter, File, Form, UploadFile

from backend.app import fixtures
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
    # TODO(alvaro): pypdf -> text -> profile.py -> insert users + seed user_memory
    return fixtures.USER


@router.get("/users/{user_id}", response_model=User)
def get_user(user_id: int):
    # TODO(alvaro): users row + active and superseded memory lines
    return fixtures.USER


@router.post("/users/{user_id}/runs", response_model=RunCreated)
def start_run(user_id: int, body: RunCreate | None = None):
    # TODO(alvaro): insert runs row, launch run.py in a BackgroundTask, return its id
    return RunCreated(run_id=fixtures.RUN.id)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int):
    return fixtures.RUN


@router.get("/users/{user_id}/brief", response_model=Brief)
def get_brief(user_id: int):
    # TODO(alvaro): latest finished run -> matches + event_matches + stats
    return fixtures.BRIEF


@router.post("/feedback", response_model=FeedbackResult)
def post_feedback(body: FeedbackIn):
    # TODO(alvaro): insert feedback, run memory.py curator, set match status
    return FeedbackResult(memory_added=[fixtures.USER.memory[2]], memory_superseded=[2])


@router.post("/jobs/{job_id}/kit", response_model=Kit)
def make_kit(job_id: int, body: KitRequest):
    # TODO(alvaro): kit.py
    return fixtures.KIT


@router.patch("/matches/{match_id}", response_model=Match)
def patch_match(match_id: int, body: MatchPatch):
    m = fixtures.MATCHES[0].model_copy(update={"status": body.status})
    return m
